/**
 * Fly.pl Filter Builder Engine (Dual-Mode Input & Live Synchronization)
 * Travel Price Monitor
 */

const DESTINATIONS = {
  egypt: { id: "egypt", code: "11:", name: "Египет", icon: "🇪🇬", subpath: "/wycieczka/egipt", defaultCeiling: 10000 },
  turkey: { id: "turkey", code: "39:", name: "Турция", icon: "🇹🇷", subpath: "/wycieczka/turcja", defaultCeiling: 12000 },
  greece: { id: "greece", code: "14:", name: "Греция", icon: "🇬🇷", subpath: "/wycieczka/grecja", defaultCeiling: 11000 },
  cyprus: { id: "cyprus", code: "12_170", name: "Кипр", icon: "🇨🇾", subpath: "/wycieczka/cypr", defaultCeiling: 11000 },
  spain: { id: "spain", code: "13:", name: "Испания", icon: "🇪🇸", subpath: "/wycieczka/hiszpania", defaultCeiling: 13000 },
  italy: { id: "italy", code: "17:", name: "Италия", icon: "🇮🇹", subpath: "/wycieczka/wlochy", defaultCeiling: 13000 },
  bulgaria: { id: "bulgaria", code: "15:", name: "Болгария", icon: "🇧🇬", subpath: "/wycieczka/bulgaria", defaultCeiling: 9000 },
  tunisia: { id: "tunisia", code: "20:", name: "Тунис", icon: "🇹🇳", subpath: "/wycieczka/tunezja", defaultCeiling: 9500 },
  uae: { id: "uae", code: "21:", name: "ОАЭ", icon: "🇦🇪", subpath: "/wycieczka/zjednoczone-emiraty-arabskie", defaultCeiling: 15000 },
};

const AIRPORTS = [
  { code: "WAW", label: "Варшава Шопен (WAW)", query: "Warszawa", defaultChecked: true },
  { code: "WMI", label: "Варшава Модлин (WMI)", query: "Warszawa - Modlin", defaultChecked: true },
  { code: "RDO", label: "Варшава Радом (RDO)", query: "Warszawa - Radom", defaultChecked: true },
  { code: "KTW", label: "Катовице (KTW)", query: "Katowice", defaultChecked: false },
  { code: "KRK", label: "Краков (KRK)", query: "Kraków", defaultChecked: false },
  { code: "GDN", label: "Гданьск (GDN)", query: "Gdańsk", defaultChecked: false },
  { code: "WRO", label: "Вроцлав (WRO)", query: "Wrocław", defaultChecked: false },
  { code: "POZ", label: "Познань (POZ)", query: "Poznań", defaultChecked: false },
  { code: "RZE", label: "Жешув (RZE)", query: "Rzeszów", defaultChecked: false },
];

function formatDateDDMMYYYY(d) {
  if (!d) return "";
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  return `${day}-${month}-${year}`;
}

function parseDateDDMMYYYY(str) {
  if (!str) return null;
  const parts = str.split(/[-.]/);
  if (parts.length === 3) {
    if (parts[0].length === 4) {
      // YYYY-MM-DD
      return new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
    }
    // DD-MM-YYYY
    return new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
  }
  return null;
}

function formatDateISO(d) {
  if (!d) return "";
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getInitialFormState() {
  const today = new Date();
  const startMin = new Date(today);
  startMin.setDate(today.getDate() + 3);

  const startMax = new Date(startMin);
  startMax.setDate(startMin.getDate() + 25);

  const returnDate = new Date(startMax);
  returnDate.setDate(startMax.getDate() + 10);

  return {
    customTitle: "",
    destination: "turkey",
    departureAirports: ["Warszawa", "Warszawa - Modlin", "Warszawa - Radom"],
    dateMode: "rolling", // "rolling" or "fixed"
    startDateMin: formatDateISO(startMin),
    startDateMax: formatDateISO(startMax),
    returnDate: formatDateISO(returnDate),
    durationFrom: 7,
    durationTo: 10,
    adults: 2,
    childrenCount: 1,
    childrenBirthdays: ["10-12-2020"],
    catering: "all_inclusive",
    categoryRating: "50",
    minPrice: 3000,
    maxPrice: 20000,
    displayCeiling: 11000,
    // Modules
    moduleArbitrageGermany: true,
    moduleHopperPredictor: true,
    moduleCohortHeatmap: true,
    moduleDealScore: true,
    moduleRoomTypes: true,
    moduleTelegramAlerts: false,
    // Germany Params
    germanyAirport: "BER",
    germanyDirectFlight: false,
  };
}

/**
 * Parses Fly.pl URL into form state attributes.
 */
function parseFlyUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  const urlClean = rawUrl.trim();
  if (!urlClean.includes("fly.pl")) return null;

  try {
    const urlObj = new URL(urlClean, "https://fly.pl");
    const params = urlObj.searchParams;
    const path = urlObj.pathname.toLowerCase();

    const result = {};

    // 1. Destination
    const destCode = params.get("destinationLocation") || params.get("filter[dest]") || "";
    let matchedDest = null;
    for (const [key, dest] of Object.entries(DESTINATIONS)) {
      if (destCode.startsWith(dest.code) || destCode === dest.code || (dest.code.includes('_') && destCode.includes(dest.code))) {
        matchedDest = key;
        break;
      }
    }
    if (!matchedDest) {
      for (const [key, dest] of Object.entries(DESTINATIONS)) {
        if (path.includes(dest.id) || (dest.subpath && path.includes(dest.subpath.split('/')[2]))) {
          matchedDest = key;
          break;
        }
      }
    }
    if (matchedDest) {
      result.destination = matchedDest;
    }

    // 2. Departure Locations
    const depRaw = params.get("departureLocation") || params.get("filter[from]") || "";
    if (depRaw) {
      const deps = depRaw.split(",").map(s => s.trim().replace(/\+/g, ' '));
      result.departureAirports = deps;
    }

    // 3. Dates
    const sMin = params.get("startDateMin") || params.get("filter[whenFrom]");
    const sMax = params.get("startDateMax") || params.get("filter[whenTo]");
    const retD = params.get("returnDate");

    if (sMin) {
      const parsedMin = parseDateDDMMYYYY(sMin);
      if (parsedMin) result.startDateMin = formatDateISO(parsedMin);
    }
    if (sMax) {
      const parsedMax = parseDateDDMMYYYY(sMax);
      if (parsedMax) result.startDateMax = formatDateISO(parsedMax);
    }
    if (retD) {
      const parsedRet = parseDateDDMMYYYY(retD);
      if (parsedRet) result.returnDate = formatDateISO(parsedRet);
    }

    // 4. Duration
    const durFrom = params.get("durationFrom");
    const durTo = params.get("durationTo");
    const durFilter = params.get("filter[duration]");
    if (durFrom) result.durationFrom = parseInt(durFrom, 10);
    if (durTo) result.durationTo = parseInt(durTo, 10);
    if (durFilter && durFilter.includes("-")) {
      const [f, t] = durFilter.split("-").map(n => parseInt(n, 10));
      if (!isNaN(f)) result.durationFrom = f;
      if (!isNaN(t)) result.durationTo = t;
    }

    // 5. Adults & Children
    const ad = params.get("adults") || params.get("filter[adults]");
    if (ad) result.adults = parseInt(ad, 10);

    const chRaw = params.get("children") || params.get("filter[child]");
    if (chRaw !== null && chRaw !== undefined) {
      if (chRaw === "" || chRaw === "0") {
        result.childrenCount = 0;
        result.childrenBirthdays = [];
      } else {
        const bdays = chRaw.split(",").map(s => s.trim()).filter(Boolean);
        result.childrenCount = bdays.length;
        result.childrenBirthdays = bdays;
      }
    }

    // 6. Catering
    const cat = params.get("catering") || params.get("filter[service]");
    if (cat) result.catering = cat.toLowerCase();

    // 7. Rating
    const rat = params.get("categoryRating") || params.get("filter[rating]");
    if (rat) result.categoryRating = rat;

    // 8. Prices
    const pFrom = params.get("priceFrom") || params.get("filter[priceFrom]");
    const pTo = params.get("priceTo") || params.get("filter[priceTo]");
    if (pFrom) result.minPrice = parseInt(pFrom, 10);
    if (pTo) {
      result.maxPrice = parseInt(pTo, 10);
      result.displayCeiling = Math.min(parseInt(pTo, 10), result.maxPrice > 12000 ? 12000 : result.maxPrice);
    }

    if (Object.keys(result).length === 0) {
      return null;
    }
    return result;
  } catch (err) {
    console.error("Error parsing Fly.pl URL:", err);
    return null;
  }
}

/**
 * Builds canonical Fly.pl search URL from state object.
 */
function buildFlyUrl(state) {
  const dest = DESTINATIONS[state.destination] || DESTINATIONS.turkey;
  const baseUrl = "https://fly.pl/szukaj-wycieczek/";
  const searchParams = new URLSearchParams();

  searchParams.set("destinationLocation", dest.code);

  if (state.departureAirports && state.departureAirports.length > 0) {
    searchParams.set("departureLocation", state.departureAirports.join(","));
  }

  // Dates
  if (state.startDateMin) {
    const dMin = parseDateDDMMYYYY(state.startDateMin) || new Date(state.startDateMin);
    searchParams.set("startDateMin", formatDateDDMMYYYY(dMin));
  }
  if (state.startDateMax) {
    const dMax = parseDateDDMMYYYY(state.startDateMax) || new Date(state.startDateMax);
    searchParams.set("startDateMax", formatDateDDMMYYYY(dMax));
  }
  if (state.returnDate) {
    const dRet = parseDateDDMMYYYY(state.returnDate) || new Date(state.returnDate);
    searchParams.set("returnDate", formatDateDDMMYYYY(dRet));
  }

  searchParams.set("adults", String(state.adults || 2));

  if (state.childrenCount > 0 && state.childrenBirthdays && state.childrenBirthdays.length > 0) {
    searchParams.set("children", state.childrenBirthdays.slice(0, state.childrenCount).join(","));
  }

  if (state.catering) {
    searchParams.set("catering", state.catering);
  }

  searchParams.set("offerTypes", "accommodation_flight");

  if (state.categoryRating) {
    searchParams.set("categoryRating", state.categoryRating);
  }

  searchParams.set("durationFrom", String(state.durationFrom || 7));
  searchParams.set("durationTo", String(state.durationTo || 10));

  if (state.minPrice) {
    searchParams.set("priceFrom", String(state.minPrice));
  }
  if (state.maxPrice) {
    searchParams.set("priceTo", String(state.maxPrice));
  }

  searchParams.set("order", "price");

  return `${baseUrl}?${searchParams.toString()}`;
}

/**
 * Builds standard configuration JSON object ready to be saved in repository.
 */
function buildFilterConfigJson(state) {
  const dest = DESTINATIONS[state.destination] || DESTINATIONS.turkey;
  const flyUrl = buildFlyUrl(state);

  // Generate clean slug and title
  const title = (state.customTitle && state.customTitle.trim())
    ? state.customTitle.trim()
    : `${dest.name} • ${state.durationFrom}–${state.durationTo} дней`;

  // Transliterate cyrillic to clean ASCII slug
  function translit(str) {
    const ruMap = {
      'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y',
      'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
      'х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
    };
    return str.toLowerCase().split('').map(ch => ruMap[ch] || ch).join('');
  }

  const rawSlugSource = (state.customTitle && state.customTitle.trim())
    ? translit(state.customTitle.trim())
    : `${state.destination}_${state.durationFrom}_${state.durationTo}`;

  const safeSlug = rawSlugSource
    .replace(/[^a-z0-9_]+/gi, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || `${state.destination}_${state.durationFrom}_${state.durationTo}`;

  const fltId = `filter_${safeSlug}`;
  const dataDir = `data/filters/${fltId}`;

  // Air ports summary
  const apCount = (state.departureAirports || []).length;
  const apShort = apCount === 3 && state.departureAirports.includes("Warszawa") ? "WAW/WMI/RDO" : (apCount ? `${apCount} аэр.` : "Любой");

  // Subtitle
  const guestsShort = state.childrenCount > 0 ? `${state.adults}+${state.childrenCount}` : `${state.adults} взр`;
  const ceiling = state.displayCeiling || state.maxPrice || 11000;
  const subtitle = `${apShort} • ${guestsShort} • ${state.durationFrom}–${state.durationTo} дн. • показ ≤${Math.round(ceiling / 1000)}k PLN`;

  const config = {
    allow_empty_offers: true,
    id: fltId,
    title: title,
    subtitle: subtitle,
    group: state.destination,
    group_label: dest.name,
    group_icon: dest.icon,
    filter_mode: state.dateMode === "fixed" ? "fixed_trip" : "dynamic_rolling",
    dynamic_search_dates: state.dateMode === "rolling",
    url: flyUrl,
    max_price_threshold: Number(state.maxPrice) || 20000,
    min_price_threshold: Number(state.minPrice) || 3000,
    display_price_ceiling: Number(state.displayCeiling) || 11000,
    history_price_ceiling: Number(state.displayCeiling) || 11000,
    data_dir: dataDir,
    output_data_file: "travel_prices.csv",
    required_offer_url_contains: [
      dest.subpath,
      "transport=accommodation_flight"
    ],
    excluded_offer_url_contains: [
      "/wycieczka/polska",
      "/wycieczka/czechy",
      "transport=accommodation&"
    ],
    wait_timeout: 30000,
    max_retries: 3,
    max_offers: 0,
    max_pages: 10,
    retry_delay: 5,
    modules: {
      arbitrage_germany: Boolean(state.moduleArbitrageGermany),
      hopper_predictor: Boolean(state.moduleHopperPredictor),
      departure_analytics: Boolean(state.moduleCohortHeatmap),
      deal_score: Boolean(state.moduleDealScore),
      room_types: Boolean(state.moduleRoomTypes),
      telegram_alerts: Boolean(state.moduleTelegramAlerts),
    },
    germany_params: {
      enabled: Boolean(state.moduleArbitrageGermany),
      departure_airport: state.germanyAirport || "BER",
      direct_flight_only: Boolean(state.germanyDirectFlight),
    },
    created_at: new Date().toISOString(),
  };

  if (state.dateMode === "fixed") {
    config.trip_anchor_date = state.startDateMin;
    config.trip_departure_slip_days = 7;
    config.retire_after = state.startDateMax;
  }

  return config;
}

/**
 * Creates pre-filled GitHub Issue URL for zero-token Issue Ops submission.
 */
function createGitHubIssueUrl(configJson) {
  const repoOwner = "Jancker2a";
  const repoName = "travel-monitoring";
  const title = `[NEW_FILTER] ${configJson.title}`;

  const body = `### ✈️ Новый фильтр мониторинга цен

**Название:** ${configJson.title}
**Направление:** ${configJson.group_icon} ${configJson.group_label}
**URL поиска Fly.pl:** [Открыть поиск на Fly.pl](${configJson.url})
**Потолок цены на витрине:** ${configJson.display_price_ceiling} PLN
**Security Token:** \`e7bbd2753119f63d1bab83262e7cf7835286942712dd1caacd25d57f24b84a56\`

\`\`\`json
${JSON.stringify(configJson, null, 2)}
\`\`\`

---
*Создано через Travel Price Monitor Filter Builder.*`;

  return `https://github.com/${repoOwner}/${repoName}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

// Export for browser and node
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    DESTINATIONS,
    AIRPORTS,
    getInitialFormState,
    parseFlyUrl,
    buildFlyUrl,
    buildFilterConfigJson,
    createGitHubIssueUrl,
    formatDateDDMMYYYY,
    formatDateISO,
    parseDateDDMMYYYY,
  };
}
