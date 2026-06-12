"""Парсер hh.ru через headless Chrome (--dump-dom), без CDP.

ЗАЧЕМ: публичный API hh.ru (api.hh.ru) с 15.12.2025 отдаёт 403 для анонимов,
а страница поиска — SPA, рендерится JS на клиенте. Обычный HTTP-парсинг не видит
вакансий. Поэтому мы запускаем настоящий Chrome в headless-режиме, он проходит
DDoS-Guard challenge, исполняет JS и печатает готовый DOM в stdout
(`--dump-dom`). Никакого CDP/Playwright/Selenium — Chrome дёргается как обычный
внешний процесс через asyncio.create_subprocess_exec, debug-порт НЕ открывается
(это и защищает от детекта автоматизации).

Слои (каждый тестируется отдельно):
1. fetch_html(url) -> str          — запуск Chrome, dump DOM, kill по таймауту.
2. parse_vacancies(html) -> [...]  — selectolax + фиксированные селекторы;
                                     детект блокировки (challenge → ошибка,
                                     не молчаливый []).
3. HhChromeSource(Source)          — строит URL поиска из Profile, пул воркеров
                                     (Semaphore), jitter, retry с бэкоффом,
                                     пагинация. Реализует тот же контракт, что и
                                     старый HhSource → подставляется в фабрику.

ВАЖНО про прод: при масштабировании потолок — это IP (один IP = риск бана hh).
Заложен хук proxy_server (--proxy-server) в конфиге. Память: headless Chrome
тяжёлый (~200-400 MB на процесс) — отсюда PARSER_CONCURRENCY и потребность в
Railway Hobby (≥1 GB). Если hh усилит защиту — менять только fetch_html/селекторы.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
import shutil
from typing import Any
from urllib.parse import urlencode

from loguru import logger
from selectolax.parser import HTMLParser, Node

from src.config import settings
from src.domain.profile import Profile
from src.domain.vacancy import ParsedVacancy
from src.sources.base import Source, SourceError, SourceRateLimitedError

# ---------------------------------------------------------------------------
# Селекторы и константы — ВСЁ хрупкое к вёрстке hh.ru собрано в одном месте.
# Если hh поменяет разметку — правим только этот блок.
# ---------------------------------------------------------------------------

SEL_CARD = '[data-qa="vacancy-serp__vacancy"]'
SEL_TITLE_LINK = '[data-qa="serp-item__title"]'
SEL_TITLE_TEXT = '[data-qa="serp-item__title-text"]'
SEL_EMPLOYER_LINK = '[data-qa="vacancy-serp__vacancy-employer"]'
SEL_EMPLOYER_TEXT = '[data-qa="vacancy-serp__vacancy-employer-text"]'
SEL_ADDRESS = '[data-qa="vacancy-serp__vacancy-address"]'
SEL_EXPERIENCE = '[data-qa^="vacancy-serp__vacancy-work-experience-"]'
_EXPERIENCE_QA_PREFIX = "vacancy-serp__vacancy-work-experience-"

# Селекторы детальной страницы /vacancy/{id}
SEL_DETAIL_DESCRIPTION = '[data-qa="vacancy-description"]'
SEL_DETAIL_SKILL = '[data-qa="skills-element"]'

# external_id / company_id достаём из href'ов карточки.
_RE_VACANCY_ID = re.compile(r"/vacancy/(\d+)")
_RE_EMPLOYER_ID = re.compile(r"/employer/(\d+)")
_RE_DIGITS_GROUP = re.compile(r"\d[\d\s ]*")

# Валюты: символ → код (совместимо со старым HhSource, который пишет "RUR").
_CURRENCY_BY_SYMBOL: dict[str, str] = {
    "₽": "RUR",
    "$": "USD",
    "€": "EUR",
    "₸": "KZT",
    "₴": "UAH",
    "Br": "BYR",
    "сўм": "UZS",
    "сум": "UZS",
}

# Маркеры легального ПУСТОГО результата (вакансий нет, но это НЕ блокировка).
_EMPTY_MARKERS = (
    "ничего не найдено",
    "по вашему запросу",
    "vacancy-search-no-results",
)
# Маркеры «оболочки» страницы поиска: шапка/контейнер выдачи рендерятся ВСЕГДА на
# валидной странице hh — даже когда карточек нет (например, ушли за последнюю
# страницу пагинации: текст "ничего не найдено" есть только на page 0). Наличие
# оболочки при нуле карточек = легальный конец выдачи, а НЕ блок/смена вёрстки.
_SERP_SHELL_MARKERS = (
    'data-qa="vacancies-search-header"',
    'data-qa="vacancy-serp__results"',
)
# Маркеры блокировки / антибот-челленджа.
# ВНИМАНИЕ: маркеры должны быть СПЕЦИФИЧНЫ. Бывшее бэрэ-слово "captcha" давало
# ложные срабатывания — на ЛЮБОЙ легальной странице hh есть i18n-строка
# "error.signup.captcha.invalid" в JS-бандле. Поэтому ловим только явные фразы
# челленджа DDoS-Guard / антибота.
_BLOCK_MARKERS = (
    "ddos-guard",
    "проверка браузера",
    "проверьте, что вы не робот",
    "подтвердите, что вы не робот",
    "are you a robot",
    "доступ ограничен",
)

# Кандидаты бинаря Chrome/Chromium при пустом CHROME_BINARY (по платформам).
_CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)
_CHROME_PATH_NAMES = ("chromium", "chromium-browser", "google-chrome", "chrome")


# ---------------------------------------------------------------------------
# Слой 1: fetch_html — запуск Chrome как внешнего процесса.
# ---------------------------------------------------------------------------


def resolve_chrome_binary() -> str:
    """Находит исполняемый Chrome/Chromium. Приоритет: CHROME_BINARY из env."""
    configured = settings.chrome_binary.strip()
    if configured:
        if not os.path.exists(configured):
            raise SourceError(f"CHROME_BINARY указан, но не найден: {configured}")
        return configured
    for candidate in _CHROME_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    for name in _CHROME_PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found
    raise SourceError(
        "Chrome/Chromium не найден. Установи Chromium или задай CHROME_BINARY."
    )


def _build_chrome_args(url: str, binary: str) -> list[str]:
    args = [
        binary,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",  # обязательно под root в Docker
        "--disable-dev-shm-usage",  # /dev/shm мал в контейнерах
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,2400",
        f"--virtual-time-budget={settings.parser_chrome_virtual_time_ms}",
    ]
    proxy = settings.parser_proxy_server.strip()
    if proxy:
        args.append(f"--proxy-server={proxy}")
    args.append("--dump-dom")
    args.append(url)
    return args


async def fetch_html(url: str, *, binary: str | None = None) -> str:
    """Запускает headless Chrome, отдаёт отрендеренный DOM как строку.

    Raises:
        SourceError: таймаут (процесс убит), ненулевой код выхода, пустой DOM.
    """
    chrome = binary or resolve_chrome_binary()
    args = _build_chrome_args(url, chrome)
    timeout = settings.parser_chrome_timeout_seconds

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as exc:
        raise SourceError(f"не удалось запустить Chrome ({chrome}): {exc}") from exc

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise SourceError(
            f"Chrome dump-dom превысил таймаут {timeout}s для {url}"
        ) from None

    if proc.returncode != 0:
        raise SourceError(f"Chrome вышел с кодом {proc.returncode} для {url}")

    html = stdout.decode("utf-8", errors="replace")
    if not html.strip():
        raise SourceError(f"Chrome вернул пустой DOM для {url}")
    return html


# ---------------------------------------------------------------------------
# Слой 2: parse_vacancies — DOM → list[ParsedVacancy] + детект блокировки.
# ---------------------------------------------------------------------------


def _clean_int(raw: str) -> int | None:
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else None


def _parse_salary(text: str) -> tuple[int | None, int | None, str | None]:
    """Парсит зарплатную строку карточки в (from, to, currency).

    Примеры hh:
      "от 100 000 ₽ за месяц, до вычета налогов" → (100000, None, RUR)
      "80 000 – 100 000 ₽ за месяц, на руки"     → (80000, 100000, RUR)
      "130 000 ₽ за месяц"                        → (130000, 130000, RUR)
      "до 200 000 ₽"                              → (None, 200000, RUR)
    """
    if not text:
        return (None, None, None)

    currency: str | None = None
    for symbol, code in _CURRENCY_BY_SYMBOL.items():
        if symbol in text:
            currency = code
            break

    # Отрезаем хвост после запятой ("до вычета налогов" / "на руки"),
    # чтобы слово "до" из квалификатора не спуталось с границей вилки.
    head = text.split(",", 1)[0]
    low = head.lower()
    nums = [n for n in (_clean_int(m) for m in _RE_DIGITS_GROUP.findall(head)) if n]

    if len(nums) >= 2:
        return (nums[0], nums[1], currency)
    if len(nums) == 1:
        value = nums[0]
        if low.lstrip().startswith("от"):
            return (value, None, currency)
        if low.lstrip().startswith("до"):
            return (None, value, currency)
        return (value, value, currency)
    return (None, None, currency)


def _extract_salary(card: Node) -> tuple[int | None, int | None, str | None]:
    """Зарплата в карточке без data-qa → ищем span с символом валюты и цифрами."""
    for span in card.css("span"):
        txt = span.text(strip=True)
        if not txt or not any(ch.isdigit() for ch in txt):
            continue
        if any(symbol in txt for symbol in _CURRENCY_BY_SYMBOL):
            return _parse_salary(txt)
    return (None, None, None)


def _first_attr(card: Node, selector: str, attr: str) -> str | None:
    node = card.css_first(selector)
    if node is None:
        return None
    value = node.attributes.get(attr)
    return value or None


def _first_text(card: Node, selector: str) -> str | None:
    node = card.css_first(selector)
    if node is None:
        return None
    text = node.text(strip=True)
    return text or None


def _extract_experience(card: Node) -> str | None:
    node = card.css_first(SEL_EXPERIENCE)
    if node is None:
        return None
    qa = node.attributes.get("data-qa") or ""
    if qa.startswith(_EXPERIENCE_QA_PREFIX):
        suffix = qa[len(_EXPERIENCE_QA_PREFIX) :].strip()
        return suffix or None
    return None


def _card_to_parsed(card: Node) -> ParsedVacancy | None:
    """Один DOM-узел карточки → ParsedVacancy. None, если нет id (мусор)."""
    title_href = _first_attr(card, SEL_TITLE_LINK, "href")
    id_match = _RE_VACANCY_ID.search(title_href or "")
    if not id_match:
        return None
    external_id = id_match.group(1)

    employer_href = _first_attr(card, SEL_EMPLOYER_LINK, "href") or ""
    employer_match = _RE_EMPLOYER_ID.search(employer_href)
    company_id = employer_match.group(1) if employer_match else None

    salary_from, salary_to, salary_currency = _extract_salary(card)
    url = title_href.split("?", 1)[0] if title_href else None

    return ParsedVacancy(
        external_id=external_id,
        source_type="hh",
        title=_first_text(card, SEL_TITLE_TEXT),
        company_name=_first_text(card, SEL_EMPLOYER_TEXT),
        company_id=company_id,
        salary_from=salary_from,
        salary_to=salary_to,
        salary_currency=salary_currency,
        url=url,
        area_name=_first_text(card, SEL_ADDRESS),
        schedule=None,  # в выдаче нет стабильно; подгрузим через fetch_details
        experience=_extract_experience(card),
        description=None,  # только в детальной карточке
        key_skills=[],  # только в детальной карточке
        published_at=None,  # в выдаче даты нет
        raw_data={"parser": "hh_chrome", "url": url},
    )


def _detect_block(html: str) -> None:
    """Бросает осмысленную ошибку, если HTML — челлендж/блок, а не выдача.

    Вызывается только когда карточек 0. Легальный пустой результат (есть маркер
    'ничего не найдено') блоком НЕ считается.
    """
    low = html.lower()
    if any(marker in low for marker in _EMPTY_MARKERS):
        return  # легальный пустой поиск — вызывающий получит []
    if any(marker in low for marker in _BLOCK_MARKERS):
        raise SourceRateLimitedError(
            "hh.ru вернул страницу-челлендж (антибот/DDoS-Guard), вакансий нет"
        )
    if any(marker in low for marker in _SERP_SHELL_MARKERS):
        return  # валидная страница поиска без карточек (вышли за последнюю страницу)
    # Ни карточек, ни маркера пустого результата, ни оболочки выдачи, ни явного
    # блока — подозрительно (сменилась вёрстка или Chrome не дорендерил). НЕ молчим.
    raise SourceError(
        "hh.ru: в DOM нет ни карточек вакансий, ни оболочки выдачи, ни маркера "
        "пустого результата (возможна смена вёрстки или скрытая блокировка)"
    )


def parse_vacancies(html: str) -> list[ParsedVacancy]:
    """DOM страницы поиска → список ParsedVacancy.

    Пустой список ВОЗВРАЩАЕТСЯ только при легальном 'ничего не найдено'.
    При блокировке/смене вёрстки — исключение (см. _detect_block).
    """
    tree = HTMLParser(html)
    cards = tree.css(SEL_CARD)
    if not cards:
        _detect_block(html)  # бросит исключение, либо вернётся (легальный empty)
        return []

    results: list[ParsedVacancy] = []
    for card in cards:
        try:
            parsed = _card_to_parsed(card)
        except Exception as exc:  # одна битая карточка не валит всю страницу
            logger.warning("hh_chrome: не разобрал карточку: {}", exc)
            continue
        if parsed is not None:
            results.append(parsed)
    return results


def parse_vacancy_detail(html: str) -> dict[str, Any]:
    """DOM детальной страницы → {"description": HTML|None, "key_skills": [...]}.

    Форма результата совместима со старым HhSource.fetch_details (hh-API JSON):
    key_skills — список словарей {"name": ...}, чтобы вызывающий код в
    api/vacancies.py не менялся.
    """
    tree = HTMLParser(html)
    desc_node = tree.css_first(SEL_DETAIL_DESCRIPTION)
    description = desc_node.html if desc_node is not None else None
    skills = [
        {"name": text}
        for node in tree.css(SEL_DETAIL_SKILL)
        if (text := node.text(strip=True))
    ]
    return {"description": description, "key_skills": skills}


# ---------------------------------------------------------------------------
# Слой 3: HhChromeSource — контракт Source (URL из профиля, пул, jitter, retry).
# ---------------------------------------------------------------------------

# Глобальный семафор ограничивает число одновременных Chrome-процессов во всём
# приложении (на источник может прийтись несколько страниц). Ленивая инициализация
# — чтобы привязаться к текущему event loop.
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.parser_concurrency))
    return _semaphore


async def _sleep_jitter() -> None:
    lo = settings.parser_jitter_min_seconds
    hi = max(lo, settings.parser_jitter_max_seconds)
    await asyncio.sleep(random.uniform(lo, hi))


# ВАЖНО: грейд профиля НЕ маппится в жёсткий фильтр hh `experience`.
# Поле опыта на hh ненадёжно — компании часто ставят "нет опыта" на вакансию с
# названием "Middle Python dev" (расширяют воронку). Жёсткий фильтр прятал такие
# хорошие вакансии из ленты. Поэтому грейд используем ТОЛЬКО в LLM-скоринге
# (он выводит реальный уровень из названия/описания), а поиск по опыту не сужаем.
# При необходимости опыт всё ещё можно задать вручную через search_params.

# Формат работы → значение фильтра hh.ru `work_format` (проверено на живой
# выдаче). ВАЖНО: старый параметр `schedule=remote` hh БОЛЬШЕ НЕ ИСПОЛЬЗУЕТ —
# актуальный фильтр это work_format. Несколько значений = ИЛИ (remote ИЛИ office).
# FIELD_WORK (разъездная) в нашей модели нет — пропускаем.
_WORK_FORMAT_TO_HH = {
    "remote": "REMOTE",
    "hybrid": "HYBRID",
    "office": "ON_SITE",
}


def build_search_url(
    profile: Profile, search_params: dict[str, Any] | None, page: int
) -> str:
    """Профиль → URL страницы поиска hh.ru (web, не API)."""
    params: dict[str, Any] = {
        "text": " ".join(profile.stack) if profile.stack else "",
        "order_by": "publication_time",
        "search_period": settings.parser_period_days,
        "page": page,
    }
    if profile.area_ids:
        params["area"] = profile.area_ids  # doseq → несколько area=
    if profile.salary_from:
        params["salary"] = profile.salary_from
        params["only_with_salary"] = "true"
    if profile.work_format:
        wf = [
            _WORK_FORMAT_TO_HH[f]
            for f in profile.work_format
            if f in _WORK_FORMAT_TO_HH
        ]
        if wf:
            params["work_format"] = wf  # doseq → несколько work_format= (ИЛИ)
    # Опыт фильтруем ТОЛЬКО по явному выбору пользователя (profile.experience),
    # а НЕ выводим из грейда: тег опыта на hh ненадёжен, грейд оценивает LLM.
    # Значения уже в формате hh (noExperience/between1And3/...), несколько = ИЛИ.
    if profile.experience:
        params["experience"] = list(profile.experience)

    if search_params:
        for key in ("text", "experience", "work_format", "order_by", "search_period"):
            if key in search_params:
                params[key] = search_params[key]

    clean = {k: v for k, v in params.items() if v not in (None, "", [])}
    qs = urlencode(clean, doseq=True)
    return f"{settings.hh_web_base_url}/search/vacancy?{qs}"


class HhChromeSource(Source):
    source_type = "hh"

    def __init__(self, *, html_fetcher: Any = None) -> None:
        # html_fetcher: для тестов можно подменить fetch_html на фейк без Chrome.
        self._fetch_html = html_fetcher or fetch_html

    async def _fetch_and_parse_page(self, url: str) -> list[ParsedVacancy]:
        retries = max(0, settings.parser_chrome_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with _get_semaphore():
                    await _sleep_jitter()
                    html = await self._fetch_html(url)
                return parse_vacancies(html)
            except (SourceError, SourceRateLimitedError) as exc:
                last_exc = exc
                logger.bind(url=url, attempt=attempt).warning(
                    "hh_chrome: попытка не удалась: {}", exc
                )
                if attempt < retries:
                    await asyncio.sleep(1.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def fetch(
        self, profile: Profile, search_params: dict[str, Any] | None = None
    ) -> list[ParsedVacancy]:
        max_pages = settings.parser_max_pages
        results: list[ParsedVacancy] = []
        seen: set[str] = set()

        for page in range(max_pages):
            url = build_search_url(profile, search_params, page)
            page_vacs = await self._fetch_and_parse_page(url)
            if not page_vacs:
                break  # легальный конец выдачи
            new_on_page = 0
            for vac in page_vacs:
                if vac.external_id in seen:
                    continue
                seen.add(vac.external_id)
                results.append(vac)
                new_on_page += 1
            # Если страница не дала ничего нового — дальше пагинировать смысла нет.
            if new_on_page == 0:
                break

        logger.bind(count=len(results), pages_scanned=page + 1).info(
            "hh_chrome: fetch завершён"
        )
        return results

    async def fetch_details(self, external_id: str) -> dict[str, Any] | None:
        """On-demand подгрузка описания + навыков со страницы /vacancy/{id}."""
        url = f"{settings.hh_web_base_url}/vacancy/{external_id}"
        retries = max(0, settings.parser_chrome_max_retries)
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                async with _get_semaphore():
                    await _sleep_jitter()
                    html = await self._fetch_html(url)
            except SourceError as exc:
                last_exc = exc
                if attempt < retries:
                    await asyncio.sleep(1.5 * (2**attempt))
                continue

            detail = parse_vacancy_detail(html)
            if detail["description"] is not None:
                return detail
            # Нет описания: либо вакансия в архиве/снята, либо челлендж.
            low = html.lower()
            if any(marker in low for marker in _BLOCK_MARKERS):
                last_exc = SourceRateLimitedError(
                    f"hh.ru челлендж на странице вакансии {external_id}"
                )
                if attempt < retries:
                    await asyncio.sleep(1.5 * (2**attempt))
                continue
            return detail  # легально нет описания
        assert last_exc is not None
        raise last_exc
