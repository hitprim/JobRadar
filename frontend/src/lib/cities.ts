/**
 * Города РФ с их area id на hh.ru (используются в фильтре поиска вакансий).
 * Список укрупнённый — крупнейшие города-миллионники + удалёнка как "вся Россия".
 *
 * area id берутся из справочника hh.ru (https://api.hh.ru/areas):
 *   113 = Россия, 1 = Москва, 2 = Санкт-Петербург, и т.д.
 */

export interface City {
  id: number;
  name: string;
}

export const CITIES: City[] = [
  { id: 1, name: "Москва" },
  { id: 2, name: "Санкт-Петербург" },
  { id: 4, name: "Новосибирск" },
  { id: 3, name: "Екатеринбург" },
  { id: 66, name: "Нижний Новгород" },
  { id: 88, name: "Казань" },
  { id: 78, name: "Самара" },
  { id: 53, name: "Краснодар" },
  { id: 68, name: "Омск" },
  { id: 76, name: "Ростов-на-Дону" },
  { id: 54, name: "Красноярск" },
  { id: 72, name: "Пермь" },
  { id: 99, name: "Уфа" },
  { id: 22, name: "Воронеж" },
  { id: 95, name: "Тюмень" },
];

export function cityName(id: number): string {
  return CITIES.find((c) => c.id === id)?.name ?? `area ${id}`;
}
