/**
 * Major cities / regions per country for globe markers.
 * Used to show clickable region points; clicking shows satellite imagery in the left panel.
 */

export interface RegionMarker {
  lat: number;
  lng: number;
  name: string;
  countryCode: string; // ISO-3
}

/** Major cities with lat, lng, name, and ISO-3 country code. */
export const MAJOR_CITIES: RegionMarker[] = [
  { lat: 34.5553, lng: 69.2075, name: "Kabul", countryCode: "AFG" },
  { lat: 36.7538, lng: 3.0588, name: "Algiers", countryCode: "DZA" },
  { lat: -33.8688, lng: 151.2093, name: "Sydney", countryCode: "AUS" },
  { lat: -15.7801, lng: -47.9292, name: "Brasília", countryCode: "BRA" },
  { lat: 23.8103, lng: 90.4125, name: "Dhaka", countryCode: "BGD" },
  { lat: 4.0511, lng: 9.7679, name: "Douala", countryCode: "CMR" },
  { lat: 50.4501, lng: 30.5234, name: "Kyiv", countryCode: "UKR" },
  { lat: 30.0444, lng: 31.2357, name: "Cairo", countryCode: "EGY" },
  { lat: 9.0320, lng: 38.7469, name: "Addis Ababa", countryCode: "ETH" },
  { lat: 33.5138, lng: 36.2765, name: "Damascus", countryCode: "SYR" },
  { lat: 33.3152, lng: 44.3661, name: "Baghdad", countryCode: "IRQ" },
  { lat: 34.0479, lng: 74.8829, name: "Srinagar", countryCode: "IND" },
  { lat: -1.2921, lng: 36.8219, name: "Nairobi", countryCode: "KEN" },
  { lat: 33.8938, lng: 35.5018, name: "Beirut", countryCode: "LBN" },
  { lat: 6.5244, lng: 3.3792, name: "Lagos", countryCode: "NGA" },
  { lat: 24.8607, lng: 67.0011, name: "Karachi", countryCode: "PAK" },
  { lat: -12.0464, lng: -77.0428, name: "Lima", countryCode: "PER" },
  { lat: 14.5995, lng: 120.9842, name: "Manila", countryCode: "PHL" },
  { lat: -33.9249, lng: 18.4241, name: "Cape Town", countryCode: "ZAF" },
  { lat: 15.5007, lng: 32.5599, name: "Khartoum", countryCode: "SDN" },
  { lat: 11.5564, lng: 104.9282, name: "Phnom Penh", countryCode: "KHM" },
  { lat: 30.0444, lng: 31.2357, name: "Cairo", countryCode: "EGY" },
  { lat: 18.5944, lng: -72.3074, name: "Port-au-Prince", countryCode: "HTI" },
  { lat: 34.0522, lng: -118.2437, name: "Los Angeles", countryCode: "USA" },
  { lat: 51.5074, lng: -0.1278, name: "London", countryCode: "GBR" },
  { lat: 48.8566, lng: 2.3522, name: "Paris", countryCode: "FRA" },
  { lat: 35.6762, lng: 139.6503, name: "Tokyo", countryCode: "JPN" },
  { lat: 19.4326, lng: -99.1332, name: "Mexico City", countryCode: "MEX" },
  { lat: -34.6037, lng: -58.3816, name: "Buenos Aires", countryCode: "ARG" },
  { lat: 41.0082, lng: 28.9784, name: "Istanbul", countryCode: "TUR" },
  { lat: 39.9042, lng: 116.4074, name: "Beijing", countryCode: "CHN" },
  { lat: -1.286389, lng: 36.817223, name: "Nairobi", countryCode: "KEN" },
  { lat: -6.2088, lng: 106.8456, name: "Jakarta", countryCode: "IDN" },
  { lat: 33.5731, lng: -7.5898, name: "Casablanca", countryCode: "MAR" },
  { lat: 12.9716, lng: 77.5946, name: "Bangalore", countryCode: "IND" },
  { lat: -33.4489, lng: -70.6693, name: "Santiago", countryCode: "CHL" },
  { lat: 5.6037, lng: -0.1870, name: "Accra", countryCode: "GHA" },
  { lat: -15.3875, lng: 28.3228, name: "Lusaka", countryCode: "ZMB" },
  { lat: -18.6657, lng: 35.5296, name: "Beira", countryCode: "MOZ" },
  { lat: 3.8792, lng: 11.5022, name: "Yaoundé", countryCode: "CMR" },
  { lat: 13.7563, lng: 100.5018, name: "Bangkok", countryCode: "THA" },
  { lat: 21.0285, lng: 105.8542, name: "Hanoi", countryCode: "VNM" },
  { lat: 14.0583, lng: 108.2772, name: "Da Nang", countryCode: "VNM" },
  { lat: 31.7683, lng: 35.2137, name: "Jerusalem", countryCode: "ISR" },
  { lat: 33.8938, lng: 35.5018, name: "Beirut", countryCode: "LBN" },
  { lat: 33.5138, lng: 36.2765, name: "Damascus", countryCode: "SYR" },
  { lat: 33.3152, lng: 44.3661, name: "Baghdad", countryCode: "IRQ" },
  { lat: 35.6892, lng: 51.3890, name: "Tehran", countryCode: "IRN" },
  { lat: 31.9454, lng: 35.9284, name: "Amman", countryCode: "JOR" },
  { lat: 15.3694, lng: 44.1910, name: "Sana'a", countryCode: "YEM" },
  { lat: 9.6412, lng: 123.8944, name: "Cebu", countryCode: "PHL" },
  { lat: 7.8731, lng: 80.7718, name: "Colombo", countryCode: "LKA" },
  { lat: 27.7172, lng: 85.3240, name: "Kathmandu", countryCode: "NPL" },
  { lat: 23.8103, lng: 90.4125, name: "Dhaka", countryCode: "BGD" },
  { lat: 16.8661, lng: 96.1951, name: "Yangon", countryCode: "MMR" },
  { lat: 11.5449, lng: 104.8922, name: "Phnom Penh", countryCode: "KHM" },
  { lat: -17.8252, lng: 31.0335, name: "Harare", countryCode: "ZWE" },
  { lat: -26.2041, lng: 28.0473, name: "Johannesburg", countryCode: "ZAF" },
  { lat: 6.5244, lng: 3.3792, name: "Lagos", countryCode: "NGA" },
  { lat: 9.0579, lng: 7.4951, name: "Abuja", countryCode: "NGA" },
  { lat: 4.3947, lng: 18.5582, name: "Bangui", countryCode: "CAF" },
  { lat: 12.1364, lng: 15.2763, name: "N'Djamena", countryCode: "TCD" },
  { lat: 4.8517, lng: 31.5895, name: "Juba", countryCode: "SSD" },
  { lat: 9.0300, lng: 38.7400, name: "Addis Ababa", countryCode: "ETH" },
  { lat: -1.9403, lng: 29.8739, name: "Kigali", countryCode: "RWA" },
  { lat: -3.3722, lng: 29.9187, name: "Bujumbura", countryCode: "BDI" },
  { lat: -4.4419, lng: 15.2663, name: "Kinshasa", countryCode: "COD" },
  { lat: 0.3476, lng: 32.5825, name: "Kampala", countryCode: "UGA" },
  { lat: -1.2921, lng: 36.8219, name: "Nairobi", countryCode: "KEN" },
  { lat: -6.3690, lng: 34.8888, name: "Dodoma", countryCode: "TZA" },
  { lat: -15.4167, lng: 28.2833, name: "Lusaka", countryCode: "ZMB" },
  { lat: -18.6657, lng: 35.5296, name: "Beira", countryCode: "MOZ" },
  { lat: -25.7479, lng: 28.2293, name: "Pretoria", countryCode: "ZAF" },
  { lat: 2.0469, lng: 45.3182, name: "Mogadishu", countryCode: "SOM" },
  { lat: 9.0192, lng: 38.7525, name: "Addis Ababa", countryCode: "ETH" },
];

/**
 * Get region markers for a given country (ISO-3) or all if code is null.
 */
export function getRegionsForCountry(countryCode: string | null): RegionMarker[] {
  if (!countryCode) return MAJOR_CITIES;
  return MAJOR_CITIES.filter((c) => c.countryCode === countryCode);
}
