// Country names match the strings Apollo's person_locations filter expects
// (plain English country names). City list is a curated set of major cities
// per country — not exhaustive — so "Other" always falls back to free text.

export const COUNTRIES: string[] = [
  "United States", "Canada", "Mexico", "United Kingdom", "Ireland",
  "France", "Germany", "Netherlands", "Belgium", "Switzerland", "Spain",
  "Italy", "Portugal", "Norway", "Sweden", "Denmark", "Finland", "Poland",
  "Austria", "Romania",
  "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Oman",
  "Bahrain", "Israel", "Turkey", "Egypt",
  "India", "China", "Japan", "South Korea", "Singapore", "Malaysia",
  "Indonesia", "Thailand", "Vietnam", "Philippines",
  "Australia", "New Zealand",
  "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Ecuador", "Venezuela",
  "Nigeria", "South Africa", "Angola", "Algeria", "Libya",
  "Russia", "Kazakhstan", "Azerbaijan",
];

// Keyed by the exact country string above.
export const CITIES_BY_COUNTRY: Record<string, string[]> = {
  "United States": [
    "Houston", "Odessa", "Midland", "Dallas", "San Antonio", "Austin",
    "New Orleans", "Oklahoma City", "Tulsa", "Denver", "Bakersfield",
    "Corpus Christi", "Beaumont", "Lafayette", "Pittsburgh", "Anchorage",
  ],
  Canada: ["Calgary", "Edmonton", "Fort McMurray", "Toronto", "Vancouver"],
  Mexico: ["Mexico City", "Villahermosa", "Ciudad del Carmen", "Monterrey", "Reynosa"],
  "United Arab Emirates": ["Dubai", "Abu Dhabi", "Sharjah"],
  "Saudi Arabia": ["Riyadh", "Dammam", "Jeddah", "Al Khobar"],
  Qatar: ["Doha"],
  Norway: ["Stavanger", "Oslo", "Bergen"],
  "United Kingdom": ["Aberdeen", "London", "Manchester"],
  Nigeria: ["Lagos", "Port Harcourt", "Abuja"],
  Brazil: ["Rio de Janeiro", "Macae", "Sao Paulo"],
  Australia: ["Perth", "Brisbane", "Sydney", "Melbourne"],
  India: ["Mumbai", "Delhi", "Chennai", "Bangalore"],
  China: ["Beijing", "Shanghai", "Shenzhen"],
  Singapore: ["Singapore"],
  Kuwait: ["Kuwait City"],
  Oman: ["Muscat"],
};

export const OTHER_CITY = "__other__";
