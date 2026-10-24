/*
 * ILIFE Vacuum Card — all-in-one Lovelace card for the ILIFE integration.
 * Vanilla JS, theme-aware, no external dependency (CSP-safe).
 * Auto-discovers the vacuum entities by translation_key (language-independent) and
 * decodes the history mini-maps (CleanMapData, 2bpp bitmap) client-side.
 */

const FLOOR_COLOR = "#c47b5e"; // cleaned floor (terracotta, like the app)
const WALL_COLOR = "#43464f";  // walls / obstacles

// ILIFE Clean `fault` bitmap labels (the problem sensor's `faults` attribute).
const FAULTS_EN = {
  bumper_fault: "Bumper stuck", obs_fault: "Obstacle sensor", wall_fault: "Wall sensor", cliff_fault: "Cliff sensor",
  land_fault: "Lifted off the floor", nosewheel_fault: "Front wheel", l_brush_fault: "Left side brush",
  r_brush_fault: "Right side brush", brush_fault: "Side brush", l_wheel_fault: "Left wheel", r_wheel_fault: "Right wheel",
  m_brush_fault: "Main brush", fan_fault: "Fan", waterpump_fault: "Water pump", air_pump_fault: "Air pump",
  garbage_fault: "Dust bin missing", water_box_fault: "Water tank missing", filter_fault: "Filter",
  battery_fault: "Battery", gyro_fault: "Gyroscope", radar_fault: "Laser sensor", camera_fault: "Camera",
  stuck_fault: "Robot stuck", flow_fault: "Water flow", other_fault: "Other fault", low_light_fault: "Too dark",
  water1_fault: "Clean water tank", water2_fault: "Dirty water tank", explore_fault: "Mapping failed",
};

const T = {
  en: {
    start: "Start", pause: "Pause", resume: "Resume", stop: "Stop", dock: "Dock", locate: "Locate",
    overview: "Overview", settings: "Settings", suction: "Suction", water: "Water", mode: "Mode",
    carpet: "Carpet recognition", manual: "Manual control", schedules: "Schedules", history: "History",
    empty_bin: "Empty bin", live: "Live", offline: "Offline", battery: "battery", last_run: "Last cleaning", floor_plan: "Floor plan", no_map: "No map yet",
    rooms: "Rooms", clean_rooms: "Clean selected",
    close: "Close", no_map_yet: "Waiting for the map image…", dirs: { forward: "Forward", backward: "Backward", left: "Left", right: "Right", rcstop: "Stop" },
    voice: "Voice", shuffle_voice: "Shuffle", mode_full: "Full", mode_rooms: "Rooms", mode_zones: "Zones", add_zone: "Add zone", clean_zones: "Clean zones", zone_hint: "Drag across the map to draw a zone", m: "m", program: "Program", efficiency: "Cleaning efficiency", y_mop: "Y-shaped mopping", carpet_boost: "Carpet boost",
    volume: "Volume", dnd: "Do not disturb", resume_after_charge: "Resume after charging", auto_empty: "Auto-empty at dock",
    cycles: "Cycles", area: "Area", total_time: "Total time", brush: "Brush", filter: "Filter",
    side_brush: "Side brush", reset: "Reset", cancel: "Cancel", reset_confirm: "Reset {part} to 100%?",
    m2_cleaned: "m² cleaned", minutes: "minutes", no_history: "No recent cleanings.",
    not_found: "No ILIFE vacuum entity found.", today: "Today", yesterday: "Yesterday",
    active: "active", session: "session", sessions: "sessions", sleeping: "standby",
    days: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    dshort: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    whole_home: "Whole home", add: "Add", save: "Save", delete: "Delete", edit_schedule: "Schedule",
    new_schedule: "New schedule", time: "Time", cycles_label: "Cycles", every_day: "Every day",
    dmini: ["M", "T", "W", "T", "F", "S", "S"], h: "h", min: "min",
    st: { cleaning: "Cleaning", docked: "Docked", returning: "Returning to dock", paused: "Paused",
          idle: "Idle", error: "Error", unavailable: "Unavailable" },
    editor_entity: "ILIFE vacuum", editor_show: "Blocks to show",
    blocks: { header: "Header", map: "Map", controls: "Start / stop buttons", rooms: "Rooms",
              overview: "Overview", consumables: "Consumables", settings: "Settings",
              schedules: "Schedules", history: "History" },
    locale: "en-US",
  },
  pl: {
    start: "Start", pause: "Pauza", resume: "Wznów", stop: "Stop", dock: "Stacja", locate: "Znajdź",
    overview: "Przegląd", settings: "Ustawienia", suction: "Ssanie", water: "Woda", mode: "Tryb",
    carpet: "Rozpoznawanie dywanów", manual: "Sterowanie ręczne", schedules: "Harmonogramy", history: "Historia",
    empty_bin: "Opróżnij pojemnik", live: "Na żywo", offline: "Offline", battery: "baterii", last_run: "Ostatnie sprzątanie", floor_plan: "Plan mieszkania", no_map: "Brak mapy",
    rooms: "Pokoje", clean_rooms: "Sprzątaj wybrane",
    close: "Zamknij", no_map_yet: "Czekam na obraz mapy…", dirs: { forward: "Do przodu", backward: "Do tyłu", left: "W lewo", right: "W prawo", rcstop: "Stop" },
    voice: "Głos", shuffle_voice: "Wymieszaj", mode_full: "Całość", mode_rooms: "Pokoje", mode_zones: "Strefy", add_zone: "Dodaj strefę", clean_zones: "Sprzątaj strefy", zone_hint: "Przeciągnij po mapie, aby narysować strefę", m: "m", program: "Program", efficiency: "Dokładność", y_mop: "Mopowanie w kształcie Y", carpet_boost: "Wzmocnienie na dywanie",
    volume: "Głośność", dnd: "Nie przeszkadzać", resume_after_charge: "Dokończ po naładowaniu", auto_empty: "Auto-opróżnianie w stacji",
    faults: {
      bumper_fault: "Zablokowany zderzak", obs_fault: "Czujnik przeszkód", wall_fault: "Czujnik ściany", cliff_fault: "Czujnik upadku",
      land_fault: "Podniesiony z podłogi", nosewheel_fault: "Przednie kółko", l_brush_fault: "Lewa szczotka boczna",
      r_brush_fault: "Prawa szczotka boczna", brush_fault: "Szczotka boczna", l_wheel_fault: "Lewe koło", r_wheel_fault: "Prawe koło",
      m_brush_fault: "Szczotka główna", fan_fault: "Wentylator", waterpump_fault: "Pompa wody", air_pump_fault: "Pompa powietrza",
      garbage_fault: "Brak pojemnika na kurz", water_box_fault: "Brak zbiornika na wodę", filter_fault: "Filtr",
      battery_fault: "Bateria", gyro_fault: "Żyroskop", radar_fault: "Czujnik laserowy", camera_fault: "Kamera",
      stuck_fault: "Robot utknął", flow_fault: "Przepływ wody", other_fault: "Inny błąd", low_light_fault: "Za ciemno",
      water1_fault: "Zbiornik czystej wody", water2_fault: "Zbiornik brudnej wody", explore_fault: "Błąd mapowania",
    },
    cycles: "Cykle", area: "Powierzchnia", total_time: "Łączny czas", brush: "Szczotka", filter: "Filtr",
    side_brush: "Szczotka boczna", reset: "Resetuj", cancel: "Anuluj", reset_confirm: "Zresetować {part} do 100%?",
    m2_cleaned: "m² posprzątane", minutes: "min", no_history: "Brak ostatnich sprzątań.",
    not_found: "Nie znaleziono odkurzacza ILIFE.", today: "Dziś", yesterday: "Wczoraj",
    active: "aktywne", session: "sprzątanie", sessions: "sprzątań",
    session_forms: { one: "sprzątanie", few: "sprzątania", many: "sprzątań", other: "sprzątania" }, sleeping: "uśpiony",
    days: ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"],
    dshort: ["Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd"],
    whole_home: "Całe mieszkanie", add: "Dodaj", save: "Zapisz", delete: "Usuń", edit_schedule: "Harmonogram",
    new_schedule: "Nowy harmonogram", time: "Godzina", cycles_label: "Cykle", every_day: "Codziennie",
    dmini: ["P", "W", "Ś", "C", "P", "S", "N"], h: "h", min: "min",
    st: { cleaning: "Sprząta", docked: "W stacji", returning: "Wraca do stacji", paused: "Wstrzymany",
          idle: "Bezczynny", error: "Błąd", unavailable: "Niedostępny" },
    editor_entity: "Odkurzacz ILIFE", editor_show: "Widoczne sekcje",
    blocks: { header: "Nagłówek", map: "Mapa", controls: "Przyciski start / stop", rooms: "Pokoje",
              overview: "Przegląd", consumables: "Materiały eksploatacyjne", settings: "Ustawienia",
              schedules: "Harmonogramy", history: "Historia" },
    locale: "pl-PL",
  },
  fr: {
    start: "Démarrer", pause: "Pause", resume: "Reprendre", stop: "Stop", dock: "Base", locate: "Localiser",
    overview: "Aperçu", settings: "Réglages", suction: "Aspiration", water: "Eau", mode: "Mode",
    carpet: "Reconnaissance des tapis", manual: "Pilotage manuel", schedules: "Programmations", history: "Historique",
    faults: {
      bumper_fault: "Pare-chocs bloqué", obs_fault: "Capteur d’obstacles", wall_fault: "Capteur de mur", cliff_fault: "Capteur de vide",
      land_fault: "Soulevé du sol", nosewheel_fault: "Roue avant", l_brush_fault: "Brosse latérale gauche",
      r_brush_fault: "Brosse latérale droite", brush_fault: "Brosse latérale", l_wheel_fault: "Roue gauche", r_wheel_fault: "Roue droite",
      m_brush_fault: "Brosse principale", fan_fault: "Ventilateur", waterpump_fault: "Pompe à eau", air_pump_fault: "Pompe à air",
      garbage_fault: "Bac à poussière absent", water_box_fault: "Réservoir d’eau absent", filter_fault: "Filtre",
      battery_fault: "Batterie", gyro_fault: "Gyroscope", radar_fault: "Capteur laser", camera_fault: "Caméra",
      stuck_fault: "Robot coincé", flow_fault: "Débit d’eau", other_fault: "Autre erreur", low_light_fault: "Trop sombre",
      water1_fault: "Réservoir d’eau propre", water2_fault: "Réservoir d’eau sale", explore_fault: "Échec de la cartographie",
    },
    empty_bin: "Vider le bac", live: "En direct", offline: "Hors ligne", battery: "batterie", last_run: "Dernier passage", floor_plan: "Plan", no_map: "Pas encore de carte",
    volume: "Volume", dnd: "Ne pas déranger", resume_after_charge: "Reprendre après la recharge", auto_empty: "Vidage automatique",
    rooms: "Pièces", clean_rooms: "Nettoyer la sélection",
    close: "Fermer", no_map_yet: "En attente de l’image de la carte…", dirs: { forward: "Avancer", backward: "Reculer", left: "Gauche", right: "Droite", rcstop: "Arrêt" },
    voice: "Voix", shuffle_voice: "Mélanger", mode_full: "Tout", mode_rooms: "Pièces", mode_zones: "Zones", add_zone: "Ajouter une zone", clean_zones: "Nettoyer les zones", zone_hint: "Glissez sur la carte pour tracer une zone", m: "m", program: "Programme", efficiency: "Efficacité de nettoyage", y_mop: "Serpillière en Y", carpet_boost: "Boost tapis",
    cycles: "Cycles", area: "Surface", total_time: "Temps cumulé", brush: "Brosse", filter: "Filtre",
    side_brush: "Brosse latérale", reset: "Réinitialiser", cancel: "Annuler", reset_confirm: "Réinitialiser {part} à 100% ?",
    m2_cleaned: "m² nettoyés", minutes: "minutes", no_history: "Aucun nettoyage récent.",
    not_found: "Aucune entité aspirateur ILIFE trouvée.", today: "Aujourd'hui", yesterday: "Hier",
    active: "active", session: "session", sessions: "sessions", sleeping: "en veille",
    days: ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
    dshort: ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    whole_home: "Toute la maison", add: "Ajouter", save: "Enregistrer", delete: "Supprimer", edit_schedule: "Programmation",
    new_schedule: "Nouvelle programmation", time: "Heure", cycles_label: "Cycles", every_day: "Tous les jours",
    dmini: ["L", "M", "M", "J", "V", "S", "D"], h: "h", min: "min",
    st: { cleaning: "Nettoyage en cours", docked: "À la base", returning: "Retour à la base", paused: "En pause",
          idle: "Inactif", error: "Erreur", unavailable: "Indisponible" },
    editor_entity: "Aspirateur ILIFE", editor_show: "Blocs affichés",
    blocks: { header: "En-tête", map: "Carte", controls: "Boutons marche / arrêt", rooms: "Pièces",
              overview: "Aperçu", consumables: "Consommables", settings: "Réglages",
              schedules: "Programmations", history: "Historique" },
    locale: "fr-FR",
  },
  ru: {
    start: "Старт", pause: "Пауза", resume: "Продолжить", stop: "Стоп", dock: "На базу", locate: "Найти",
    overview: "Обзор", settings: "Настройки", suction: "Всасывание", water: "Вода", mode: "Режим",
    carpet: "Распознавание ковров", manual: "Ручное управление", schedules: "Расписания", history: "История",
    empty_bin: "Очистить пылесборник", live: "Сейчас", offline: "Не в сети", battery: "батареи", last_run: "Последняя уборка", floor_plan: "План", no_map: "Карты пока нет",
    rooms: "Комнаты", clean_rooms: "Убрать выбранные",
    close: "Закрыть", no_map_yet: "Жду изображение карты…", dirs: { forward: "Вперёд", backward: "Назад", left: "Влево", right: "Вправо", rcstop: "Стоп" },
    voice: "Озвучка", shuffle_voice: "Перемешать", mode_full: "Полная", mode_rooms: "Комнаты", mode_zones: "Зоны", add_zone: "Добавить зону", clean_zones: "Убрать зоны", zone_hint: "Проведите пальцем по карте, чтобы нарисовать зону", m: "м", program: "Программа", efficiency: "Тщательность уборки", y_mop: "Y-образная влажная уборка", carpet_boost: "Усиление на коврах",
    volume: "Громкость", dnd: "Не беспокоить", resume_after_charge: "Продолжить после зарядки", auto_empty: "Автоочистка на базе",
    faults: {
      bumper_fault: "Застрял бампер", obs_fault: "Датчик препятствий", wall_fault: "Датчик стены", cliff_fault: "Датчик перепада",
      land_fault: "Поднят с пола", nosewheel_fault: "Переднее колесо", l_brush_fault: "Левая боковая щётка",
      r_brush_fault: "Правая боковая щётка", brush_fault: "Боковая щётка", l_wheel_fault: "Левое колесо", r_wheel_fault: "Правое колесо",
      m_brush_fault: "Основная щётка", fan_fault: "Вентилятор", waterpump_fault: "Водяной насос", air_pump_fault: "Воздушный насос",
      garbage_fault: "Нет пылесборника", water_box_fault: "Нет бака для воды", filter_fault: "Фильтр",
      battery_fault: "Батарея", gyro_fault: "Гироскоп", radar_fault: "Лазерный датчик", camera_fault: "Камера",
      stuck_fault: "Робот застрял", flow_fault: "Подача воды", other_fault: "Другая ошибка", low_light_fault: "Слишком темно",
      water1_fault: "Бак чистой воды", water2_fault: "Бак грязной воды", explore_fault: "Ошибка построения карты",
    },
    cycles: "Уборки", area: "Площадь", total_time: "Общее время", brush: "Основная щётка", filter: "Фильтр",
    side_brush: "Боковая щётка", reset: "Сбросить", cancel: "Отмена", reset_confirm: "Сбросить ресурс «{part}» до 100%?",
    keep_case: true,
    m2_cleaned: "м² убрано", minutes: "мин", no_history: "Недавних уборок нет.",
    not_found: "Пылесос ILIFE не найден.", today: "Сегодня", yesterday: "Вчера",
    active: "вкл.", session: "уборка", sessions: "уборок", sleeping: "спит",
    session_forms: { one: "уборка", few: "уборки", many: "уборок", other: "уборки" },
    days: ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    dshort: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    whole_home: "Весь дом", add: "Добавить", save: "Сохранить", delete: "Удалить", edit_schedule: "Расписание",
    new_schedule: "Новое расписание", time: "Время", cycles_label: "Циклы", every_day: "Каждый день",
    dmini: ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"], h: " ч ", min: " мин",
    st: { cleaning: "Уборка", docked: "На базе", returning: "Едет на базу", paused: "Пауза",
          idle: "Ожидание", error: "Ошибка", unavailable: "Недоступен" },
    editor_entity: "Пылесос ILIFE", editor_show: "Показывать блоки",
    blocks: { header: "Заголовок", map: "Карта", controls: "Кнопки старт / стоп", rooms: "Комнаты",
              overview: "Обзор", consumables: "Расходники", settings: "Настройки",
              schedules: "Расписания", history: "История" },
    locale: "ru-RU",
  },
};

// Display units of the area and duration sensors, in m² and minutes.
const M2_PER = { "m²": 1, "cm²": 1e-4, "mm²": 1e-6, "km²": 1e6, ha: 1e4, "in²": 6.4516e-4,
                 "ft²": 0.09290304, "yd²": 0.83612736, ac: 4046.8564224, "mi²": 2589988.110336 };
const MIN_PER = { "μs": 1 / 6e7, ms: 1 / 60000, s: 1 / 60, min: 1, h: 60, d: 1440, w: 10080 };

// Blocks the `show` option can list, in card order; leaving it out shows them all.
const BLOCKS = ["header", "map", "controls", "rooms", "overview", "consumables", "settings", "schedules", "history"];

function cardLang(hass) {
  const lang = ((hass && (hass.language || hass.locale?.language)) || "en").toLowerCase();
  return Object.keys(T).find((l) => l !== "en" && lang.startsWith(l)) || "en";
}

function decodeCleanMap(b64) {
  if (!b64) return null;
  let bin;
  try { bin = atob(b64); } catch (e) { return null; }
  const b = new Uint8Array(bin.length);
  for (let i = 0; i < b.length; i++) b[i] = bin.charCodeAt(i);
  if (b.length < 5 || b[0] !== 0x01) return null;
  const BPR = b[1] || 3;
  const rows = Math.floor((b.length - 2) / BPR);
  const cells = [];
  for (let r = 0; r < rows; r++) {
    for (let by = 0; by < BPR; by++) {
      const val = b[2 + r * BPR + by];
      for (let p = 0; p < 4; p++) {
        const t = (val >> ((3 - p) * 2)) & 0x3;
        if (t === 1 || t === 2) cells.push({ x: by * 4 + p, y: r, t });
      }
    }
  }
  return { w: BPR * 4, h: rows, cells };
}

// `path` (ILIFE Clean history): cleaning runs as flat [x0, y0, x1, y1, ...] lists
// in the same cells as `cells`, drawn over the map.
function drawMapCells(canvas, cells, maxW, maxH, path) {
  const ctx = canvas.getContext("2d");
  if (!cells || !cells.length) { canvas.width = 1; canvas.height = 1; ctx.clearRect(0, 0, 1, 1); return; }
  let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity, n1 = 0, n2 = 0;
  for (const c of cells) {
    if (c.x < minx) minx = c.x; if (c.x > maxx) maxx = c.x; if (c.y < miny) miny = c.y; if (c.y > maxy) maxy = c.y;
    if (c.t === 1) n1++; else n2++;
  }
  const floorType = n1 >= n2 ? 1 : 2;
  const cw = maxx - minx + 1, ch = maxy - miny + 1;
  const MG = Math.max(3, Math.round(Math.max(cw, ch) * 0.1));
  const cols = cw + 2 * MG, rows = ch + 2 * MG, cell = 10;
  const W = cols * cell, H = rows * cell;
  canvas.width = W; canvas.height = H;
  const s = Math.min(maxW / W, maxH / H);
  canvas.style.width = Math.max(1, Math.round(W * s)) + "px";
  canvas.style.height = Math.max(1, Math.round(H * s)) + "px";
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, W, H);
  for (const c of cells) {
    ctx.fillStyle = c.t === floorType ? FLOOR_COLOR : WALL_COLOR;
    ctx.fillRect((c.x - minx + MG) * cell, (c.y - miny + MG) * cell, cell, cell);
  }
  if (path && path.length) {
    ctx.strokeStyle = "rgba(255,255,255,.9)";
    ctx.lineWidth = cell * 0.5;
    ctx.lineJoin = ctx.lineCap = "round";
    const px = (v) => (v - minx + MG + 0.5) * cell, py = (v) => (v - miny + MG + 0.5) * cell;
    for (const run of path) {
      ctx.beginPath();
      for (let i = 0; i + 1 < run.length; i += 2) {
        if (i) ctx.lineTo(px(run[i]), py(run[i + 1])); else ctx.moveTo(px(run[i]), py(run[i + 1]));
      }
      ctx.stroke();
    }
  }
}

// The map camera's `calibration_points` (three vacuum cell -> image pixel pairs) as
// an affine map both ways, or null when the camera has none. Cells are the robot's
// frame (y up) that ilife.clean_zone takes; pixels are the camera image's own.
function zoneCalibration(attrs) {
  try { return zoneCalibrationOf(attrs && attrs.calibration_points); } catch (err) { return null; }
}
function zoneCalibrationOf(pts) {
  if (!Array.isArray(pts) || pts.length < 3) return null;
  const [p0, p1, p2] = pts;
  const a = p1.vacuum.x - p0.vacuum.x, b = p2.vacuum.x - p0.vacuum.x;
  const c = p1.vacuum.y - p0.vacuum.y, d = p2.vacuum.y - p0.vacuum.y;
  const det = a * d - b * c;
  if (!det) return null;
  // M maps a vacuum offset to a pixel offset: M = [m1 m2] * [[a b] [c d]]^-1.
  const m1x = p1.map.x - p0.map.x, m2x = p2.map.x - p0.map.x;
  const m1y = p1.map.y - p0.map.y, m2y = p2.map.y - p0.map.y;
  const M = [(m1x * d - m2x * c) / det, (m2x * a - m1x * b) / det,
    (m1y * d - m2y * c) / det, (m2y * a - m1y * b) / det];
  const mdet = M[0] * M[3] - M[1] * M[2];
  if (!mdet) return null;
  return {
    toPx: (x, y) => {
      const dx = x - p0.vacuum.x, dy = y - p0.vacuum.y;
      return [p0.map.x + M[0] * dx + M[1] * dy, p0.map.y + M[2] * dx + M[3] * dy];
    },
    toCell: (px, py) => {
      const dx = px - p0.map.x, dy = py - p0.map.y;
      return [p0.vacuum.x + (M[3] * dx - M[1] * dy) / mdet, p0.vacuum.y + (M[0] * dy - M[2] * dx) / mdet];
    },
  };
}

const MAX_ZONES = 5;

const esc = (x) => String(x).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class IlifeVacuumCard extends HTMLElement {
  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    // `show`: the blocks to render, as a list (or "a, b"); absent or empty = all of them.
    let show = config.show;
    if (typeof show === "string") show = show.split(",").map((x) => x.trim()).filter(Boolean);
    if (show !== undefined && !Array.isArray(show)) throw new Error("show: expected a list of blocks");
    const bad = (show || []).filter((b) => !BLOCKS.includes(b));
    if (bad.length) throw new Error(`show: unknown block ${bad.join(", ")} (use ${BLOCKS.join(", ")})`);
    this._show = new Set(show && show.length ? show : BLOCKS);
    this._config = config;
    this._built = false;
    this._padOpen = false;
    this._drag = null;
    this.innerHTML = "";
  }
  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;
    // Home Assistant hands a new hass on every state change anywhere: skip the
    // render when none of this vacuum's entities (nor the language) changed.
    if (this._built && prev && this._watch && prev.language === hass.language && prev.locale === hass.locale
        && this._watch.every((id) => prev.states[id] === hass.states[id])) return;
    this._lang = cardLang(hass);
    // The room list is part of the layout: rebuild when the app's rooms change.
    // So is the Zones mode, once the map camera has shown a calibration (it is not
    // taken away again when the camera blinks unavailable).
    const vac = this._ent?.vacuum || this._config.entity;
    const camId = this._ent?.map;
    if (camId && zoneCalibration(hass.states[camId]?.attributes)) this._calSeen = true;
    // And the voice packs on offer.
    const voiceId = this._ent?.voice;
    const roomSig = JSON.stringify(hass.states[vac]?.attributes.rooms || {}) + (this._calSeen ? "|zones" : "")
      + (voiceId ? JSON.stringify(hass.states[voiceId]?.attributes.options || []) : "");
    if (this._built && roomSig !== this._roomSig) this._built = false;
    this._roomSig = roomSig;
    if (!this._built) this._build();
    this._update();
  }
  get _t() { return T[this._lang] || T.en; }
  _has(block) { return !this._show || this._show.has(block); }
  // Dates in the user's HA language; the clock as their profile says (12/24 h).
  _locale() { return this._hass?.locale?.language || this._hass?.language || this._t.locale; }
  _timeOpts() {
    const tf = this._hass?.locale?.time_format, o = { hour: "2-digit", minute: "2-digit" };
    if (tf === "12") o.hour12 = true;
    else if (tf === "24") o.hour12 = false;
    return o;
  }
  _timeLocale() { return this._hass?.locale?.time_format === "system" ? undefined : this._locale(); }
  _plural(n) {
    const t = this._t, forms = t.session_forms;
    if (!forms) return n > 1 ? t.sessions : t.session;
    let cat = "other";
    try { cat = new Intl.PluralRules(t.locale).select(n); } catch (err) { /* old browser */ }
    return forms[cat] || forms.other;
  }
  getCardSize() { return 14; }
  static getStubConfig(hass) {
    const vac = Object.keys(hass.states).find(
      (e) => e.startsWith("vacuum.") && (!hass.entities || hass.entities[e]?.platform === "ilife"));
    return { entity: vac || "" };
  }
  static getConfigElement() { return document.createElement("ilife-vacuum-card-editor"); }

  _resolve() {
    const hass = this._hass, reg = hass.entities || {};
    const cfgEnt = this._config.entity;
    const deviceId = cfgEnt && reg[cfgEnt] ? reg[cfgEnt].device_id : null;
    let ids = deviceId
      ? Object.values(reg).filter((x) => x.device_id === deviceId).map((x) => x.entity_id)
      : Object.values(reg).filter((x) => x.platform === "ilife").map((x) => x.entity_id);
    if (!ids.length && cfgEnt) ids = [cfgEnt];
    const tk = (id) => reg[id]?.translation_key || "";
    const dom = (id) => id.split(".")[0];
    const e = { vacuum: cfgEnt || null, map: null, water: null, mode: null, carpet: null,
      efficiency: null, program: null, voice: null, voiceshuffle: null, ymop: null, boost: null, tsched: null,
      dnd: null, resume: null, autoempty: null, volume: null, problem: null,
      battery: null, history: null, online: null, brush: null, side: null, filter: null,
      curarea: null, curtime: null, totalarea: null, totaltime: null, totalcount: null,
      buttons: {}, schedules: {} };
    for (const id of ids) {
      const d = dom(id), k = tk(id);
      if (d === "vacuum") { if (!e.vacuum) e.vacuum = id; }
      else if (d === "camera") { if (k === "map" || !e.map) e.map = id; }
      else if (d === "binary_sensor") { if (k === "online") e.online = id; else if (k === "problem") e.problem = id; }
      else if (d === "number") { if (k === "volume") e.volume = id; }
      else if (d === "select") {
        if (k === "water_level") e.water = id;
        else if (k === "cleaning_mode") e.mode = id;
        else if (k === "cleaning_efficiency") e.efficiency = id;
        else if (k === "cleaning_program") e.program = id;
        else if (k === "voice_pack") e.voice = id;
      }
      else if (d === "switch") {
        if (k === "carpet") e.carpet = id;
        else if (k === "y_mop") e.ymop = id;
        else if (k === "carpet_boost") e.boost = id;
        else if (k === "do_not_disturb") e.dnd = id;
        else if (k === "resume_after_charge") e.resume = id;
        else if (k === "auto_empty") e.autoempty = id;
        else { const m = k.match(/^schedule_(\d+)_enable$/); if (m) (e.schedules[+m[1]] = e.schedules[+m[1]] || {}).enable = id; }
      } else if (d === "time") {
        const m = k.match(/^schedule_(\d+)_time$/); if (m) (e.schedules[+m[1]] = e.schedules[+m[1]] || {}).time = id;
      } else if (d === "button") {
        const map = { forward: "forward", backward: "backward", left: "left", right: "right", rc_pause: "rcstop", dust_collection: "dust",
          reset_main_brush: "resetmain", reset_side_brush: "resetside", reset_filter: "resetfilter" };
        if (map[k]) e.buttons[map[k]] = id;
        else if (k === "shuffle_voice_now") e.voiceshuffle = id;
      } else if (d === "sensor") {
        const dc = hass.states[id]?.attributes.device_class;
        if (dc === "battery") e.battery = id;
        else if (k === "history") e.history = id;
        else if (k === "schedules") e.tsched = id;
        else if (k === "main_brush") e.brush = id;
        else if (k === "side_brush") e.side = id;
        else if (k === "filter") e.filter = id;
        else if (k === "current_area") e.curarea = id;
        else if (k === "current_time") e.curtime = id;
        else if (k === "total_area") e.totalarea = id;
        else if (k === "total_time") e.totaltime = id;
        else if (k === "total_count") e.totalcount = id;
      }
    }
    return e;
  }

  _seg(label, key, opts, stateObj, attr) {
    if (!opts || !opts.length) return "";
    // Show an option the way Home Assistant translates it ("plan_1" -> "Plan 1",
    // "strong" -> "Сильная") from the integration's state translations; the raw
    // value stays the data-val. `attr`: the option is that attribute's value.
    const hass = this._hass;
    const fmt = (o) => !stateObj ? o
      : attr ? (hass.formatEntityAttributeValue ? hass.formatEntityAttributeValue(stateObj, attr, o) : o)
      : (hass.formatEntityState ? hass.formatEntityState(stateObj, o) : o);
    return `<div class="vc-field"><div class="vc-mlabel">${label}</div>
      <div class="vc-seg" data-seg="${key}" style="--n:${opts.length}">
        <div class="vc-thumb"></div>
        ${opts.map((o) => `<button class="vc-pill" data-val="${esc(o)}">${esc(fmt(o))}</button>`).join("")}
      </div></div>`;
  }

  _build() {
    if (!this._hass) return;
    this._tschedSig = null;  // the schedule list is re-rendered into the new DOM
    const hass = this._hass, t = this._t;
    this._ent = this._resolve();
    const e = this._ent;
    if (!e.vacuum) { this.innerHTML = `<ha-card><div style="padding:18px">${t.not_found}</div></ha-card>`; this._built = true; return; }
    const vs = hass.states[e.vacuum] || { attributes: {} };
    const dir = (id, icon) => e.buttons[id] ? `<button class="vc-dir" data-act="${id}" aria-label="${t.dirs?.[id] || id}"><ha-icon icon="${icon}"></ha-icon></button>` : `<span></span>`;

    let sched = "";
    for (let n = 1; n <= 7; n++) {
      const s = e.schedules[n]; if (!s || (!s.enable && !s.time)) continue;
      sched += `<div class="vc-lrow">
        <span class="vc-sday">${t.days[n - 1]}</span>
        ${s.time ? `<input type="time" class="vc-stime" data-ent="${s.time}">` : "<span></span>"}
        ${s.enable ? `<label class="vc-switch"><input type="checkbox" class="vc-sen" data-ent="${s.enable}"><span class="vc-slider"></span></label>` : ""}
      </div>`;
    }
    const strip = t.days.map((d, i) => `<span class="vc-daypill" data-day="${i + 1}">${(t.dmini || [])[i] || d[0]}</span>`).join("");
    // ILIFE Clean laser models: {room id: name as in the app} (vacuum attribute).
    const rooms = vs.attributes.rooms || {};
    const roomIds = Object.keys(rooms).sort((a, b) => a - b);
    const toggles = [[e.carpet, "mdi:rug", t.carpet], [e.boost, "mdi:rug", t.carpet_boost],
      [e.ymop, "mdi:alpha-y-circle-outline", t.y_mop], [e.autoempty, "mdi:delete-restore", t.auto_empty],
      [e.resume, "mdi:battery-sync", t.resume_after_charge], [e.dnd, "mdi:bell-sleep", t.dnd]].filter(([id]) => id);
    const vol = e.volume && hass.states[e.volume];
    const has = (b) => this._has(b);
    const showMap = has("map") && e.map, showRooms = has("rooms") && roomIds.length;
    // Full / Rooms / Zones, as in the app: with the start button, the mode decides
    // what it starts. Without it the rooms block keeps its own button.
    if (e.map && zoneCalibration(hass.states[e.map]?.attributes)) this._calSeen = true;
    const canZone = showMap && has("controls") && !!this._calSeen;
    const modes = has("controls") ? ["full", ...(showRooms ? ["rooms"] : []), ...(canZone ? ["zones"] : [])] : [];
    this._modes = modes;
    this._drag = null;
    // The mode the user picked survives a mode being unavailable for a while.
    this._mode = modes.includes(this._wantMode) ? this._wantMode : "full";
    // The entities whose changes re-render the card (see set hass).
    const ids = [];
    const walk = (v) => { if (typeof v === "string" && v.includes(".")) ids.push(v); else if (v && typeof v === "object") Object.values(v).forEach(walk); };
    walk(e);
    this._watch = [...new Set(ids)];

    this.innerHTML = `
      <ha-card class="ilife-card">
        <style>
          ha-card.ilife-card{margin:0 auto;display:block;}
          .vc{--e1:0 1px 2px rgba(0,0,0,.06),0 1px 3px rgba(0,0,0,.10);
              --hover:color-mix(in srgb, var(--primary-text-color) 6%, var(--secondary-background-color));
              padding:16px;color:var(--primary-text-color);
              font-family:var(--ha-font-family,var(--paper-font-body1_-_font-family),system-ui,sans-serif);}
          @media(min-width:480px){.vc{padding:20px;}}
          .vc *{box-sizing:border-box;}
          /* Responsive: single column on narrow, two columns when the card is wide
             (PC). The .wide class is toggled by a ResizeObserver on the card's own
             width, so it adapts to its placement, not the viewport. */
          /* Masonry-style auto-balancing: each section is an unbreakable block;
             the browser spreads them across 2 (>=560px) or 3 (>=900px) columns to
             even out the heights. Single column on narrow. */
          /* Wide/panel = a "bento" of rounded tiles on the auto-balancing grid. */
          .vc.wide .vc-cols{column-count:var(--cols,2);column-gap:18px;}
          .vc.wide .vc-block{
            background:color-mix(in srgb, var(--primary-text-color) 6%, var(--ha-card-background,var(--card-background-color)));
            border:1px solid color-mix(in srgb, var(--primary-text-color) 12%, transparent);border-radius:22px;padding:16px 18px;margin-top:18px;
            box-shadow:0 2px 10px rgba(0,0,0,.12);
            break-inside:avoid;-webkit-column-break-inside:avoid;}
          .vc.wide .vc-block>:first-child{margin-top:0;}
          .vc.wide .vc-block .vc-sec{margin:0 0 12px;}
          .vc.wide .vc-kpi{background:transparent;border-color:transparent;padding:6px 4px;}
          .vc.wide .vc-map{margin-top:0;}
          /* full_height: fill the whole panel (width AND height) as a bento grid.
             Map = big hero (2x2), the four other tiles fill the right side. */
          .vc.full{display:flex;flex-direction:column;box-sizing:border-box;height:calc(100dvh - var(--header-height, 56px) - 12px);}
          .vc.full .vc-cols{column-count:unset;display:grid;
            grid-template-columns:repeat(4,1fr);grid-template-rows:1fr 1fr;gap:16px;
            flex:1;min-height:0;}
          .vc.full .vc-block{margin-top:0;min-height:0;overflow:auto;}
          .vc.full .blk-map{grid-column:1 / 3;grid-row:1 / 3;overflow:auto;display:flex;flex-direction:column;}
          .vc.full .blk-map .vc-map{min-height:260px;}
          .vc.full .blk-map .vc-map{aspect-ratio:auto;flex:1;min-height:0;}
          .vc.full .blk-stats{grid-column:3;grid-row:1;}
          .vc.full .blk-settings{grid-column:3;grid-row:2;}
          .vc.full .blk-sched{grid-column:4;grid-row:1;}
          .vc.full .blk-history{grid-column:4;grid-row:2;}
          /* no schedules -> history fills the whole right column instead of leaving a gap */
          .vc.full .vc-cols:not(:has(.blk-sched)) .blk-history{grid-row:1 / 3;}
          /* full mode content: scale up + distribute so tiles aren't half-empty */
          .vc.full .vc-block{padding:22px 26px;display:flex;flex-direction:column;}
          .vc.full .vc-mlabel{font-size:13px;}
          .vc.full .vc-sec{margin:0 0 18px;}
          .vc.full .vc-sec .r{font-size:13px;}
          .vc.full .blk-stats .vc-kpis{flex:1;grid-template-columns:repeat(2,1fr);grid-auto-rows:1fr;gap:16px;}
          .vc.full .blk-stats .vc-kpi{display:flex;flex-direction:column;justify-content:center;background:color-mix(in srgb,var(--primary-text-color) 4%,transparent);border:1px solid color-mix(in srgb,var(--primary-text-color) 9%,transparent);border-radius:18px;padding:14px 20px;}
          .vc.full .blk-stats .vc-kpi:last-child:nth-child(odd){grid-column:1 / -1;}
          .vc.full .blk-stats .vc-kpi .ic{width:38px;height:38px;margin-bottom:10px;}
          .vc.full .blk-stats .vc-kpi .ic ha-icon{--mdc-icon-size:22px;}
          .vc.full .blk-stats .vc-kpi .v{font-size:30px;}
          .vc.full .blk-stats .vc-kpi .l{font-size:12px;margin-top:6px;}
          .vc.full .blk-settings{justify-content:space-between;}
          .vc.full .blk-settings .vc-field{margin:0;}
          .vc.full .blk-settings .vc-seg{height:46px;}
          .vc.full .blk-settings .vc-pill{font-size:14px;}
          .vc.full .blk-settings .vc-lrow{padding:14px 4px;}
          .vc.full .blk-settings .vc-lrow .lbl{font-size:15px;}
          .vc.full .blk-settings .vc-fold{padding:14px 4px;}
          .vc.full .blk-sched .vc-list{display:flex;flex-direction:column;flex:1;justify-content:space-between;}
          .vc.full .blk-sched .vc-lrow{padding:10px 6px;}
          .vc.full .blk-sched .vc-sday{font-size:16px;}
          .vc.full .blk-sched .vc-stime{font-size:15px;padding:8px 12px;}
          .vc.full .blk-sched .vc-daypill{width:30px;height:30px;font-size:13px;}
          .vc.full .blk-history .vc-hist{max-height:none;flex:1;}
          .vc.full .blk-history .vc-hrow{padding:12px 8px;}
          .vc.full .blk-history .vc-hwhen{font-size:15px;}
          .vc.full .blk-history .vc-hsub{font-size:13px;}
          .vc.full .blk-history .vc-harea{font-size:14px;}
          .vc.full .blk-history .vc-hthumb{width:42px;height:42px;}
          /* full mode: let the hero map fill its big tile (lift the 70%/78% + 360x260 caps) */
          .vc.full .blk-map canvas.vc-mapimg{max-width:none;max-height:none;}
          .vc.full .blk-map img.vc-mapimg{width:auto;height:96%;max-width:96%;}
          .vc [hidden]{display:none!important;}
          .vc-num{font-variant-numeric:tabular-nums;font-feature-settings:'tnum';}
          .vc-mlabel{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--secondary-text-color);}
          .vc-sec{display:flex;align-items:center;justify-content:space-between;margin:24px 0 10px;}
          .vc-sec .r{font-size:12px;color:var(--secondary-text-color);}
          .vc-head{display:flex;align-items:center;gap:12px;min-height:52px;}
          .vc-ava{position:relative;width:44px;height:44px;flex:none;border-radius:50%;display:flex;align-items:center;justify-content:center;
            background:color-mix(in srgb,var(--primary-color) 12%,transparent);color:var(--primary-color);box-shadow:inset 0 0 0 1px var(--divider-color);}
          .vc-ava ha-icon{--mdc-icon-size:24px;}
          .vc-dot{position:absolute;right:-1px;bottom:-1px;width:12px;height:12px;border-radius:50%;background:var(--disabled-text-color);
            box-shadow:0 0 0 2px var(--ha-card-background,var(--card-background-color));}
          .vc.online .vc-dot{background:var(--success-color,#43a047);}
          .vc.cleaning .vc-dot{animation:vcpulse 2s infinite;}
          @keyframes vcpulse{0%,100%{box-shadow:0 0 0 2px var(--card-background-color),0 0 0 4px color-mix(in srgb,var(--success-color,#43a047) 45%,transparent);}50%{box-shadow:0 0 0 2px var(--card-background-color),0 0 0 8px transparent;}}
          .vc.offline .vc-ava{opacity:.55;}
          .vc-id{flex:1;min-width:0;}
          .vc-name{font-size:17px;font-weight:600;letter-spacing:-.01em;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
          .vc-state{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--secondary-text-color);line-height:1.2;margin-top:1px;}
          .vc.cleaning .vc-state{color:var(--primary-color);}
          .vc-batt{display:flex;align-items:center;gap:6px;height:28px;padding:4px 10px;border-radius:999px;background:var(--secondary-background-color);
            font-size:13px;font-weight:600;position:relative;overflow:hidden;flex:none;}
          .vc-batt ha-icon{--mdc-icon-size:17px;}
          .vc-battbar{position:absolute;left:0;bottom:0;height:3px;background:currentColor;border-radius:2px;transition:width .3s;}
          .vc-map{position:relative;margin-top:14px;border-radius:18px;background:var(--secondary-background-color);
            aspect-ratio:4/3;overflow:hidden;box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--divider-color) 70%,transparent);
            display:flex;align-items:center;justify-content:center;}
          .vc-map .grid{position:absolute;inset:0;pointer-events:none;opacity:.5;
            background-image:repeating-linear-gradient(0deg,transparent 0 15px,color-mix(in srgb,var(--divider-color) 30%,transparent) 15px 16px),
                             repeating-linear-gradient(90deg,transparent 0 15px,color-mix(in srgb,var(--divider-color) 30%,transparent) 15px 16px);}
          .vc-map .glow{position:absolute;inset:0;pointer-events:none;background:radial-gradient(120% 120% at 50% 35%,color-mix(in srgb,var(--primary-color) 9%,transparent),transparent 60%);}
          .vc-map .vig{position:absolute;inset:0;pointer-events:none;box-shadow:inset 0 -30px 40px -30px rgba(0,0,0,.25);}
          .vc-mapimg{position:relative;max-width:70%;max-height:78%;object-fit:contain;z-index:1;filter:drop-shadow(0 4px 10px rgba(0,0,0,.25));}
          .vc.offline .vc-mapimg{filter:saturate(.5) opacity(.7);}
          .vc-nomap{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:6px;font-size:13px;color:var(--secondary-text-color);}
          .vc-nomap ha-icon{--mdc-icon-size:28px;opacity:.6;}
          .vc-badge{position:absolute;top:10px;left:10px;z-index:3;display:flex;align-items:center;gap:5px;font-size:11px;font-weight:600;
            padding:4px 10px;border-radius:999px;background:color-mix(in srgb,var(--card-background-color) 72%,transparent);
            color:var(--secondary-text-color);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--divider-color) 60%,transparent);backdrop-filter:blur(6px);}
          .vc-badge .bd{width:6px;height:6px;border-radius:50%;background:var(--error-color,#e74c3c);}
          .vc.cleaning .vc-badge .bd{animation:vcpulse2 1.6s infinite;}
          @keyframes vcpulse2{0%,100%{opacity:1;}50%{opacity:.35;}}
          .vc.offline .vc-badge .bd{background:var(--disabled-text-color);animation:none;}
          .vc-scrim{position:absolute;left:0;right:0;bottom:0;z-index:2;padding:22px 14px 10px;display:flex;gap:10px;align-items:baseline;
            background:linear-gradient(transparent,color-mix(in srgb,var(--card-background-color) 85%,transparent));font-size:12px;color:var(--secondary-text-color);}
          .vc-scrim b{font-size:14px;font-weight:700;color:var(--primary-text-color);}
          .vc-modal{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;}
          .vc-modal-bg{position:absolute;inset:0;background:rgba(0,0,0,.62);backdrop-filter:blur(3px);}
          .vc-modal-panel{position:relative;z-index:1;background:var(--card-background-color);border:1px solid var(--divider-color);
            border-radius:20px;padding:16px;width:auto;max-width:min(94vw,640px);max-height:90vh;overflow:auto;
            box-shadow:0 16px 48px rgba(0,0,0,.5);display:flex;flex-direction:column;gap:14px;}
          .vc-modal-head{display:flex;align-items:center;justify-content:space-between;gap:12px;}
          .vc-modal-head .t{font-size:15px;font-weight:600;}
          .vc-modal-head button{width:32px;height:32px;flex:none;border:none;border-radius:50%;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);font-size:15px;}
          .vc-modal-map{background:var(--secondary-background-color);border-radius:14px;padding:16px;display:flex;align-items:center;justify-content:center;box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--divider-color) 70%,transparent);}
          .vc-modal-map canvas{image-rendering:pixelated;max-width:100%;max-height:66vh;width:auto;height:auto;border-radius:6px;filter:drop-shadow(0 4px 10px rgba(0,0,0,.25));}
          .vc-modal-stats{display:flex;justify-content:center;gap:36px;padding:2px 0 4px;}
          .vc-modal-stats .s{text-align:center;}
          .vc-modal-stats .v{font-size:22px;font-weight:700;color:var(--primary-color);}
          .vc-modal-stats .l{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--secondary-text-color);margin-top:2px;}
          .vc-cta{width:100%;height:48px;margin-top:14px;border:none;border-radius:14px;cursor:pointer;
            background:var(--primary-color);color:var(--text-primary-color,#fff);font-size:15px;font-weight:600;
            display:flex;align-items:center;justify-content:center;gap:8px;box-shadow:0 4px 14px color-mix(in srgb,var(--primary-color) 30%,transparent);transition:.15s;}
          .vc-cta:hover{background:color-mix(in srgb,var(--primary-color) 88%,white);}
          .vc-cta:active{transform:scale(.985);}
          .vc-cta ha-icon{--mdc-icon-size:20px;}
          .vc-cta:disabled{opacity:.5;cursor:default;transform:none;}
          .vc-secs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px;}
          .vc-sbtn{height:54px;border:1px solid var(--divider-color);border-radius:12px;background:transparent;cursor:pointer;color:var(--secondary-text-color);
            display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;font-size:11px;font-weight:600;transition:.15s;}
          .vc-sbtn:hover{background:var(--hover);color:var(--primary-text-color);transform:translateY(-1px);}
          .vc-sbtn ha-icon{--mdc-icon-size:22px;}
          .vc-sbtn.stop:hover{color:var(--error-color,#db4437);}
          /* When "offline" the vacuum is usually just Wi-Fi asleep at the dock —
             Start/Stop/Dock/Locate must stay clickable (they wake it). Only the
             live directional pad is disabled. */
          .vc-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:8px;}
          .vc-kpi{position:relative;background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:14px;padding:12px;}
          .vc-kpi-reset{position:absolute;top:8px;right:8px;z-index:2;width:26px;height:26px;border:none;border-radius:999px;cursor:pointer;
            background:color-mix(in srgb,var(--primary-text-color) 8%,transparent);color:var(--secondary-text-color);
            display:flex;align-items:center;justify-content:center;opacity:.55;transition:.15s;}
          .vc-kpi-reset:hover{opacity:1;background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color);}
          .vc-kpi-reset ha-icon{--mdc-icon-size:16px;}
          .vc-confirm{max-width:min(92vw,380px);text-align:center;}
          .vc-confirm-msg{font-size:15px;font-weight:500;line-height:1.4;padding:6px 4px 4px;}
          .vc-confirm-btns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px;}
          .vc-cbtn{height:44px;border:none;border-radius:12px;cursor:pointer;font-size:14px;font-weight:600;transition:.15s;}
          .vc-cbtn.cancel{background:var(--secondary-background-color);color:var(--primary-text-color);}
          .vc-cbtn.ok{background:var(--primary-color);color:var(--text-primary-color,#fff);}
          .vc-cbtn:active{transform:scale(.97);}
          .vc-kpi .ic{width:28px;height:28px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--primary-color) 12%,transparent);color:var(--primary-color);margin-bottom:8px;}
          .vc-kpi .ic ha-icon{--mdc-icon-size:17px;}
          .vc-kpi .v{font-size:20px;font-weight:700;line-height:1;}
          .vc-kpi .l{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--secondary-text-color);margin-top:4px;}
          .vc-gauge{height:4px;border-radius:3px;background:var(--divider-color);margin-top:8px;overflow:hidden;}
          .vc-gauge>i{display:block;height:100%;background:var(--primary-color);border-radius:3px;}
          .vc-field{margin:12px 0;}
          .vc-field .vc-mlabel{margin-bottom:6px;}
          .vc-seg{position:relative;display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));background:var(--secondary-background-color);border-radius:999px;padding:3px;height:38px;}
          .vc-thumb{position:absolute;top:3px;bottom:3px;left:3px;width:calc((100% - 6px)/var(--n));border-radius:999px;background:var(--card-background-color);box-shadow:var(--e1);transition:transform .2s cubic-bezier(.2,.8,.2,1);}
          .vc-thumb.hidden{opacity:0;}
          .vc-pill{position:relative;z-index:1;min-width:0;padding:0 4px;border:none;background:transparent;cursor:pointer;font-size:13px;font-weight:500;color:var(--secondary-text-color);transition:color .15s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
          .vc-pill.active{color:var(--primary-text-color);font-weight:600;}
          /* Labels too long for equal segments (a narrow column, long translations):
             the control wraps into a row of pills instead of cutting them to "str…". */
          .vc-seg.wrap,.vc.full .blk-settings .vc-seg.wrap{display:flex;flex-wrap:wrap;gap:3px;height:auto;border-radius:19px;}
          .vc-seg.wrap .vc-thumb{display:none;}
          .vc-seg.wrap .vc-pill{flex:1 1 auto;padding:7px 12px;border-radius:999px;white-space:normal;}
          .vc-seg.wrap .vc-pill.active{background:var(--card-background-color);box-shadow:var(--e1);}
          .vc-list{border-radius:14px;overflow:hidden;}
          .vc-lrow{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:12px;padding:12px 4px;}
          .vc-lrow + .vc-lrow{border-top:1px solid color-mix(in srgb,var(--divider-color) 60%,transparent);}
          .vc-lrow .lbl{display:flex;align-items:center;gap:10px;font-size:14px;}
          .vc-lrow .lbl ha-icon{--mdc-icon-size:20px;color:var(--secondary-text-color);}
          .vc-sday{font-size:14px;}
          .vc-stime{padding:6px 8px;border-radius:10px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);font-size:14px;font-weight:600;}
          .vc-switch{position:relative;display:inline-block;width:44px;height:24px;flex:none;}
          .vc-switch input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:pointer;z-index:1;}
          .vc-switch input:focus-visible + .vc-slider{outline:2px solid var(--primary-color);outline-offset:2px;}
          .vc-slider{position:absolute;inset:0;background:var(--divider-color);border-radius:24px;transition:.2s;cursor:pointer;}
          .vc-slider:before{content:"";position:absolute;height:18px;width:18px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s;}
          .vc-switch input:checked + .vc-slider{background:var(--primary-color);}
          .vc-switch input:checked + .vc-slider:before{transform:translateX(20px);}
          .vc-fold{display:flex;align-items:center;justify-content:space-between;cursor:pointer;padding:12px 4px;user-select:none;}
          .vc-fold .chev{transition:transform .2s;color:var(--secondary-text-color);}
          .vc.padopen .vc-fold .chev{transform:rotate(180deg);}
          .vc-pad{display:grid;grid-template-columns:repeat(3,48px);gap:8px;justify-content:center;padding:4px 0 6px;}
          .vc-dir{width:48px;height:48px;border:1px solid var(--divider-color);border-radius:50%;background:transparent;cursor:pointer;color:var(--secondary-text-color);display:flex;align-items:center;justify-content:center;transition:.15s;}
          .vc-dir:hover{background:var(--hover);color:var(--primary-text-color);}
          .vc-dir:active{transform:scale(.9);}
          .vc-dir ha-icon{--mdc-icon-size:22px;}
          .vc-rooms .vc-sec{margin:18px 0 8px;}
          .vc-passes{display:flex;gap:4px;background:var(--secondary-background-color);border-radius:999px;padding:3px;}
          .vc-pass{border:none;background:transparent;border-radius:999px;padding:3px 10px;cursor:pointer;font-size:12px;font-weight:600;color:var(--secondary-text-color);}
          .vc-pass.on{background:var(--card-background-color);color:var(--primary-text-color);box-shadow:var(--e1);}
          .vc-chips{display:flex;flex-wrap:wrap;gap:6px;}
          .vc-chip{border:1px solid var(--divider-color);background:transparent;border-radius:999px;padding:7px 14px;cursor:pointer;font-size:13px;font-weight:500;color:var(--primary-text-color);transition:.15s;}
          .vc-chip:hover{background:var(--hover);}
          .vc-chip.on{background:color-mix(in srgb,var(--primary-color) 16%,transparent);border-color:var(--primary-color);color:var(--primary-color);font-weight:600;}
          .vc-rgo{width:100%;height:42px;margin-top:10px;border:none;border-radius:12px;cursor:pointer;background:color-mix(in srgb,var(--primary-color) 14%,transparent);
            color:var(--primary-color);font-size:14px;font-weight:600;display:flex;align-items:center;justify-content:center;gap:8px;transition:.15s;}
          .vc-rgo:disabled{opacity:.45;cursor:default;}
          .vc-modes{margin-top:14px;}
          .vc.zoning .vc-map{aspect-ratio:1/1;}
          .vc.zoning .vc-mapimg{max-width:94%;max-height:94%;}
          .vc-zones{position:absolute;z-index:4;touch-action:none;cursor:crosshair;}
          .vc.zoning .vc-scrim,.vc.zoning .vc-badge{pointer-events:none;}
          .vc-zbtn::before{content:"";position:absolute;inset:-9px;border-radius:50%;}
          .vc-pass{min-height:32px;min-width:40px;}
          .vc-sadd{min-height:34px;}
          .vc-vshuf{display:flex;justify-content:flex-end;margin-top:-4px;}
          .vc-zone{position:absolute;pointer-events:auto;touch-action:none;cursor:move;border:2px dashed #fff;
            background:color-mix(in srgb,var(--primary-color) 32%,transparent);box-shadow:0 0 0 1px rgba(0,0,0,.25);}
          .vc-zbtn{position:absolute;width:26px;height:26px;border-radius:50%;border:none;padding:0;background:#fff;color:var(--primary-color);
            display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.35);touch-action:none;}
          .vc-zbtn ha-icon{--mdc-icon-size:16px;pointer-events:none;}
          .vc-zdel{top:-13px;right:-13px;cursor:pointer;}
          .vc-zrs{bottom:-13px;right:-13px;cursor:nwse-resize;}
          .vc-zsize{position:absolute;left:0;right:0;top:100%;margin-top:4px;text-align:center;font-size:12px;font-weight:600;white-space:nowrap;
            color:var(--primary-text-color);text-shadow:0 0 3px var(--card-background-color),0 0 3px var(--card-background-color);pointer-events:none;}
          .vc-zbar{display:flex;align-items:center;gap:10px;margin-top:10px;}
          .vc-zbar .vc-zhint{flex:1;min-width:0;font-size:12px;color:var(--secondary-text-color);}
          .vc-sadd:disabled{opacity:.45;cursor:default;}
          .vc-problem{display:flex;align-items:center;gap:5px;margin-top:3px;font-size:12px;font-weight:600;color:var(--error-color,#db4437);}
          .vc-problem ha-icon{--mdc-icon-size:15px;}
          .vc-volrow{grid-template-columns:auto 1fr auto;}
          .vc-range{width:100%;accent-color:var(--primary-color);}
          .vc-volval{font-size:13px;font-weight:600;color:var(--secondary-text-color);min-width:38px;text-align:right;}
          .vc-sechead{display:flex;align-items:center;gap:10px;}
          .vc-sadd{display:flex;align-items:center;gap:4px;border:none;border-radius:999px;padding:4px 10px 4px 6px;cursor:pointer;font-size:12px;font-weight:600;
            background:color-mix(in srgb,var(--primary-color) 14%,transparent);color:var(--primary-color);}
          .vc-sadd ha-icon{--mdc-icon-size:16px;}
          .vc-trow{cursor:pointer;border-radius:12px;transition:.12s;}
          .vc-trow:hover{background:var(--hover);}
          .vc-trow.off{opacity:.55;}
          .vc-tmeta{display:grid;grid-template-columns:auto 1fr;column-gap:12px;align-items:baseline;min-width:0;}
          .vc-ttime{font-size:20px;font-weight:700;grid-row:1 / 3;}
          .vc-tdays{font-size:13px;font-weight:600;}
          .vc-tsum{font-size:12px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
          .vc-sedit{min-width:min(92vw,380px);}
          .vc-srow{display:flex;align-items:center;justify-content:space-between;gap:12px;}
          .vc-setime{font-size:18px;padding:6px 12px;}
          .vc-sedays .vc-chip{flex:1;padding:7px 0;text-align:center;}
          .vc-rgo ha-icon{--mdc-icon-size:18px;}
          .vc-dust{width:100%;height:44px;margin-top:2px;border:1px solid var(--divider-color);border-radius:12px;background:transparent;cursor:pointer;color:var(--secondary-text-color);display:flex;align-items:center;justify-content:center;gap:8px;font-size:13px;font-weight:600;}
          .vc-dust:hover{background:var(--hover);color:var(--primary-text-color);}
          .vc-strip{display:flex;gap:6px;margin-bottom:8px;}
          .vc-daypill{width:26px;height:26px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600;background:transparent;color:var(--secondary-text-color);}
          .vc-daypill.on{background:color-mix(in srgb,var(--primary-color) 16%,transparent);color:var(--primary-color);}
          .vc-hist{max-height:230px;overflow-y:auto;-webkit-mask-image:linear-gradient(to bottom,#000 88%,transparent);}
          .vc-hrow{display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;gap:12px;padding:8px 6px;border-radius:12px;cursor:pointer;transition:.12s;}
          .vc-hrow:hover{background:var(--hover);}
          .vc-hthumb{width:34px;height:34px;border-radius:8px;background:var(--secondary-background-color);display:flex;align-items:center;justify-content:center;overflow:hidden;box-shadow:inset 0 0 0 1px var(--divider-color);}
          .vc-hthumb canvas{image-rendering:pixelated;max-width:100%;max-height:100%;}
          .vc-hmeta{min-width:0;}
          .vc-hwhen{font-size:14px;font-weight:600;line-height:1.2;}
          .vc-hsub{font-size:12px;color:var(--secondary-text-color);}
          .vc-harea{font-size:13px;font-weight:600;}
          .vc-hchev{color:var(--secondary-text-color);--mdc-icon-size:18px;}
          .vc-empty{padding:14px;color:var(--secondary-text-color);font-size:13px;text-align:center;}
          @media(prefers-reduced-motion:reduce){.vc *{animation:none!important;transition:none!important;}}
        </style>
        <div class="vc" data-el="root">
          ${has("header") ? `<div class="vc-head">
            <div class="vc-ava"><ha-icon icon="mdi:robot-vacuum"></ha-icon><span class="vc-dot"></span></div>
            <div class="vc-id"><div class="vc-name" data-el="name"></div><div class="vc-state"><span data-el="state"></span></div>
              <div class="vc-problem" data-el="problem" hidden><ha-icon icon="mdi:alert-circle"></ha-icon><span data-el="problemtxt"></span></div></div>
            <div class="vc-batt vc-num" data-el="batt"><ha-icon data-el="batticon" icon="mdi:battery"></ha-icon><span data-el="battval"></span><i class="vc-battbar" data-el="battbar"></i></div>
          </div>` : ""}
          <div class="vc-cols">
          ${showMap || has("controls") || showRooms ? `<div class="vc-block blk-map">
          ${showMap ? `<div class="vc-map">
            <div class="glow"></div><div class="grid"></div>
            <img class="vc-mapimg" data-el="map" alt="${t.blocks.map}">
            <canvas class="vc-mapimg" data-el="heromap" hidden></canvas>
            ${canZone ? `<div class="vc-zones" data-el="zones" hidden></div>` : ""}
            <div class="vc-nomap" data-el="nomap" hidden><ha-icon icon="mdi:map-search-outline"></ha-icon><span>${t.no_map}</span></div>
            <div class="vig"></div>
            <span class="vc-badge"><span class="bd"></span><span data-el="badgetxt">${t.live}</span></span>
            <div class="vc-scrim vc-num" data-el="scrim" hidden></div>
          </div>` : ""}
          ${modes.length > 1 ? `<div class="vc-seg vc-modes" data-seg="cmode" style="--n:${modes.length}"><div class="vc-thumb"></div>
            ${modes.map((m) => `<button class="vc-pill" data-val="${m}">${t["mode_" + m]}</button>`).join("")}</div>` : ""}
          ${canZone ? `<div class="vc-zbar" data-el="zbar" hidden>
            <button class="vc-sadd" data-el="zadd"><ha-icon icon="mdi:plus"></ha-icon>${t.add_zone}</button>
            <span class="vc-zhint" data-el="zhint">${t.zone_hint}</span>
            <div class="vc-passes">${[1, 2].map((n) => `<button class="vc-pass" data-zpass="${n}">${n}×</button>`).join("")}</div>
          </div>` : ""}
          ${showRooms ? `<div class="vc-rooms" data-el="rooms">
            <div class="vc-sec"><span class="vc-mlabel">${t.rooms}</span>
              <div class="vc-passes">${[1, 2].map((n) => `<button class="vc-pass" data-pass="${n}">${n}×</button>`).join("")}</div></div>
            <div class="vc-chips">${roomIds.map((id) => `<button class="vc-chip" data-room="${esc(id)}">${esc(rooms[id])}</button>`).join("")}</div>
            <button class="vc-rgo" data-el="roomgo" disabled${has("controls") ? " hidden" : ""}><ha-icon icon="mdi:broom"></ha-icon><span data-el="roomgotxt">${t.clean_rooms}</span></button>
          </div>` : ""}
          ${has("controls") ? `<button class="vc-cta" data-el="cta"><ha-icon data-el="ctaicon" icon="mdi:play"></ha-icon><span data-el="ctatxt">${t.start}</span></button>
          <div class="vc-secs">
            <button class="vc-sbtn stop" data-act="stop"><ha-icon icon="mdi:stop"></ha-icon><span>${t.stop}</span></button>
            <button class="vc-sbtn" data-act="dock"><ha-icon icon="mdi:home-import-outline"></ha-icon><span>${t.dock}</span></button>
            <button class="vc-sbtn" data-act="locate"><ha-icon icon="mdi:map-marker"></ha-icon><span>${t.locate}</span></button>
          </div>` : ""}
          </div>` : ""}
          ${has("overview") || has("consumables") ? `<div class="vc-block blk-stats">
          <div class="vc-sec"><span class="vc-mlabel">${has("overview") ? t.overview : t.blocks.consumables}</span></div>
          <div class="vc-kpis" data-el="kpis"></div>
          </div>` : ""}
          ${has("settings") ? `<div class="vc-block blk-settings">
          <div class="vc-sec"><span class="vc-mlabel">${t.settings}</span></div>
          ${this._seg(t.suction, "fan", (vs.attributes.fan_speed_list) || [], hass.states[e.vacuum], "fan_speed")}
          ${this._seg(t.water, "water", (e.water && hass.states[e.water]?.attributes.options) || [], e.water && hass.states[e.water])}
          ${this._seg(t.mode, "mode", (e.mode && hass.states[e.mode]?.attributes.options) || [], e.mode && hass.states[e.mode])}
          ${this._seg(t.program, "prog", (e.program && hass.states[e.program]?.attributes.options) || [], e.program && hass.states[e.program])}
          ${this._seg(t.efficiency, "eff", (e.efficiency && hass.states[e.efficiency]?.attributes.options) || [], e.efficiency && hass.states[e.efficiency])}
          ${this._seg(t.voice, "voice", (e.voice && hass.states[e.voice]?.attributes.options) || [], e.voice && hass.states[e.voice])}
          ${e.voice && e.voiceshuffle ? `<div class="vc-vshuf"><button class="vc-sadd" data-el="voiceshuffle"><ha-icon icon="mdi:shuffle"></ha-icon>${t.shuffle_voice}</button></div>` : ""}
          ${toggles.length ? `<div class="vc-list">${toggles.map(([id, icon, label]) => `<div class="vc-lrow"><span class="lbl"><ha-icon icon="${icon}"></ha-icon>${label}</span><span></span>
            <label class="vc-switch"><input type="checkbox" class="vc-tog" data-ent="${id}"><span class="vc-slider"></span></label></div>`).join("")}</div>` : ""}
          ${vol ? `<div class="vc-lrow vc-volrow"><span class="lbl"><ha-icon icon="mdi:volume-high"></ha-icon>${t.volume}</span>
            <input type="range" class="vc-range" data-el="volume" min="${vol.attributes.min ?? 0}" max="${vol.attributes.max ?? 100}" step="${vol.attributes.step ?? 10}">
            <span class="vc-volval vc-num" data-el="volval"></span></div>` : ""}
          ${Object.keys(e.buttons).length ? `
          <div class="vc-fold" data-el="fold" role="button" tabindex="0"><span class="vc-mlabel">${t.manual}</span><ha-icon class="chev" icon="mdi:chevron-down"></ha-icon></div>
          <div data-el="padbox" hidden>
            <div class="vc-pad">
              <span></span>${dir("forward", "mdi:arrow-up-bold")}<span></span>
              ${dir("left", "mdi:arrow-left-bold")}${dir("rcstop", "mdi:pause")}${dir("right", "mdi:arrow-right-bold")}
              <span></span>${dir("backward", "mdi:arrow-down-bold")}<span></span>
            </div>
            ${e.buttons.dust ? `<button class="vc-dust" data-act="dust"><ha-icon icon="mdi:delete-empty"></ha-icon>${t.empty_bin}</button>` : ""}
          </div>` : ""}
          </div>` : ""}
          ${sched && has("schedules") ? `<div class="vc-block blk-sched"><div class="vc-sec"><span class="vc-mlabel">${t.schedules}</span><span class="r" data-el="schedcount"></span></div>
            <div class="vc-strip">${strip}</div><div class="vc-list">${sched}</div></div>` : ""}
          ${e.tsched && has("schedules") ? `<div class="vc-block blk-sched"><div class="vc-sec"><span class="vc-mlabel">${t.schedules}</span>
            <span class="r vc-sechead"><span data-el="tschedcount"></span><button class="vc-sadd" data-el="tschedadd"><ha-icon icon="mdi:plus"></ha-icon>${t.add}</button></span></div>
            <div class="vc-strip">${strip}</div><div class="vc-list" data-el="tschedlist"></div></div>` : ""}
          ${has("history") ? `<div class="vc-block blk-history">
          <div class="vc-sec"><span class="vc-mlabel">${t.history}</span><span class="r" data-el="histcount"></span></div>
          <div class="vc-hist" data-el="hist"></div>
          </div>` : ""}
          </div>
          <div class="vc-modal" data-el="modal" hidden>
            <div class="vc-modal-bg" data-el="modalbg"></div>
            <div class="vc-modal-panel">
              <div class="vc-modal-head"><span class="t" data-el="mcap"></span><button data-el="mclose" aria-label="${t.close}">✕</button></div>
              <div class="vc-modal-map"><canvas data-el="mcanvas"></canvas></div>
              <div class="vc-modal-stats vc-num" data-el="mstats"></div>
            </div>
          </div>
          <div class="vc-modal" data-el="confirm" hidden>
            <div class="vc-modal-bg" data-el="confirmbg"></div>
            <div class="vc-modal-panel vc-confirm">
              <div class="vc-confirm-msg" data-el="confirmmsg"></div>
              <div class="vc-confirm-btns">
                <button class="vc-cbtn cancel" data-el="confirmno">${t.cancel}</button>
                <button class="vc-cbtn ok" data-el="confirmyes">${t.reset}</button>
              </div>
            </div>
          </div>
          ${e.tsched && has("schedules") ? `<div class="vc-modal" data-el="sedit" hidden>
            <div class="vc-modal-bg" data-el="seditbg"></div>
            <div class="vc-modal-panel vc-sedit">
              <div class="vc-modal-head"><span class="t" data-el="sedittitle"></span><button data-el="seditclose" aria-label="${t.close}">✕</button></div>
              <div class="vc-srow"><span class="vc-mlabel">${t.time}</span><input type="time" class="vc-stime vc-setime" data-el="setime"></div>
              <div class="vc-chips vc-sedays">${t.dshort.map((d, i) => `<button class="vc-chip" data-day="${i}">${d}</button>`).join("")}</div>
              <div class="vc-seg" data-el="setype" style="--n:${roomIds.length ? 2 : 1}"><div class="vc-thumb"></div>
                <button class="vc-pill" data-val="global">${t.whole_home}</button>
                ${roomIds.length ? `<button class="vc-pill" data-val="rooms">${t.rooms}</button>` : ""}</div>
              <div class="vc-chips vc-serooms" data-el="serooms">${roomIds.map((id) => `<button class="vc-chip" data-room="${id}">${esc(rooms[id])}</button>`).join("")}</div>
              <div class="vc-srow"><span class="vc-mlabel">${t.cycles_label}</span>
                <div class="vc-passes">${[1, 2, 3].map((n) => `<button class="vc-pass" data-cyc="${n}">${n}×</button>`).join("")}</div></div>
              <div class="vc-confirm-btns">
                <button class="vc-cbtn cancel" data-el="sedel">${t.delete}</button>
                <button class="vc-cbtn ok" data-el="sesave">${t.save}</button>
              </div>
            </div>
          </div>` : ""}
        </div>`;

    this._wire();
    this._built = true;
    this._startMapTimer();
    this._observeWidth();
  }

  _observeWidth() {
    const root = this.querySelector('[data-el="root"]');
    if (!root || typeof ResizeObserver === "undefined") return;
    if (this._ro) this._ro.disconnect();
    this._ro = new ResizeObserver((ents) => {
      const w = ents[0].contentRect.width;
      // One column per ~360px, capped at the number of sections shown: the card
      // fills a wide/panel placement, yet stays narrow inside a grid column.
      const blocks = this.querySelectorAll(".vc-block").length || 1;
      const cols = Math.max(1, Math.min(blocks, Math.round(w / 360)));
      root.style.setProperty("--cols", cols);
      root.classList.toggle("wide", cols >= 2);
      // full-page bento: auto when the card takes ~all the width (single-card /
      // panel view); off in a normal grid column. `full_height` config overrides.
      const near = w / (window.innerWidth || w) >= 0.78;
      const cfg = this._config || {};
      // The bento grid places all five tiles: only with the map tile, and only by
      // itself when nothing is hidden.
      const wantFull = cfg.full_height !== undefined ? !!cfg.full_height && !!this.querySelector(".blk-map")
        : near && this._show.size === BLOCKS.length;
      root.classList.toggle("full", wantFull && w >= 900);
      this._scheduleFit();
    });
    this._ro.observe(root);
    // Refit the hero map whenever its tile changes size (full-page mode grows it).
    if (this._roMap) this._roMap.disconnect();
    this._roMap = null;
    const mbox = this.querySelector(".blk-map .vc-map");
    if (mbox && typeof ResizeObserver !== "undefined") {
      this._roMap = new ResizeObserver(() => this._scheduleFit());
      this._roMap.observe(mbox);
    }
  }

  // Coalesce refit calls from both observers into at most one draw per frame.
  _scheduleFit() {
    if (this._fitRaf) return;
    const raf = (typeof requestAnimationFrame === "function") ? requestAnimationFrame : (cb) => cb();
    this._fitRaf = raf(() => { this._fitRaf = 0; this._fitHero(); this._fitSegs(); this._layoutZones(); });
  }

  // A segmented control whose labels don't fit its equal segments wraps (see .wrap).
  _fitSegs() {
    this.querySelectorAll(".blk-settings .vc-seg").forEach((seg) => {
      seg.classList.remove("wrap");
      const cut = [...seg.querySelectorAll(".vc-pill")].some((p) => p.scrollWidth > p.clientWidth + 1);
      seg.classList.toggle("wrap", cut);
    });
  }

  _fitHero() {
    const hero = this.querySelector('[data-el="heromap"]');
    if (!hero || hero.hidden || !this._heroCells || !this._heroCells.length) return;
    const box = hero.parentElement; if (!box) return;               // .vc-map
    const full = this.querySelector('[data-el="root"]')?.classList.contains("full");
    let mw = 360, mh = 260, key = "nf";
    if (full) {
      const r = box.getBoundingClientRect();
      if (r.width < 40 || r.height < 40) return;                     // not laid out yet
      mw = r.width - 28; mh = r.height - 28;
      key = "f:" + Math.round(r.width) + "x" + Math.round(r.height);
    }
    // Skip redundant redraws (esp. resize-driven) when nothing relevant changed.
    if (key === this._fitKey && this._fitCells === this._heroCells) return;
    this._fitKey = key; this._fitCells = this._heroCells;
    drawMapCells(hero, this._heroCells, mw, mh);
  }

  _wire() {
    const hass = this._hass, e = this._ent;
    const call = (dom, srv, data) => hass.callService(dom, srv, data);
    const q = (s) => this.querySelector(`[data-el="${s}"]`);
    q("cta")?.addEventListener("click", () => {
      const st = hass.states[e.vacuum]?.state;
      if (st === "cleaning") call("vacuum", "pause", { entity_id: e.vacuum });
      // A paused clean resumes whatever it was, whichever mode is shown.
      else if (st === "paused" || this._mode === "full") call("vacuum", "start", { entity_id: e.vacuum });
      else if (this._mode === "rooms") this._cleanRooms(call);
      else if (this._mode === "zones" && this._zones.length) {
        call("ilife", "clean_zone", { entity_id: e.vacuum, repeats: this._zonePasses,
          zone: this._zones.map((z) => [Math.round(z[0]), Math.round(z[1]), Math.round(z[2]), Math.round(z[3])]) });
      }
    });
    this.querySelectorAll(".vc-sbtn").forEach((b) => b.addEventListener("click", () => {
      const a = b.dataset.act;
      if (a === "stop") call("vacuum", "stop", { entity_id: e.vacuum });
      else if (a === "dock") call("vacuum", "return_to_base", { entity_id: e.vacuum });
      else if (a === "locate") call("vacuum", "locate", { entity_id: e.vacuum });
    }));
    this.querySelectorAll(".vc-dir,.vc-dust").forEach((b) => b.addEventListener("click", () => {
      const a = b.dataset.act; if (e.buttons[a]) call("button", "press", { entity_id: e.buttons[a] });
    }));
    this.querySelectorAll(".vc-seg").forEach((seg) => seg.addEventListener("click", (ev) => {
      const pill = ev.target.closest(".vc-pill"); if (!pill) return;
      const key = seg.dataset.seg, val = pill.dataset.val;
      if (key === "cmode") { this._mode = this._wantMode = val; this._saveZones(); this._update(); }
      else if (key === "fan") call("vacuum", "set_fan_speed", { entity_id: e.vacuum, fan_speed: val });
      else if (key === "water") call("select", "select_option", { entity_id: e.water, option: val });
      else if (key === "mode") call("select", "select_option", { entity_id: e.mode, option: val });
      else if (key === "eff") call("select", "select_option", { entity_id: e.efficiency, option: val });
      else if (key === "prog") call("select", "select_option", { entity_id: e.program, option: val });
      else if (key === "voice") call("select", "select_option", { entity_id: e.voice, option: val });
    }));
    this.querySelectorAll(".vc-tog").forEach((c) => c.addEventListener("change", () => call("switch", c.checked ? "turn_on" : "turn_off", { entity_id: c.dataset.ent })));
    q("volume")?.addEventListener("input", (ev) => { q("volval").textContent = ev.target.value + "%"; });
    q("volume")?.addEventListener("change", (ev) => call("number", "set_value", { entity_id: e.volume, value: Number(ev.target.value) }));
    // Room selection lives in the card until "Clean selected" sends it.
    this._roomSel = new Set([...(this._roomSel || [])].filter((id) => this.querySelector(`.vc-rooms .vc-chip[data-room="${id}"]`)));
    this._passes = this._passes || 1;
    this.querySelectorAll(".vc-rooms .vc-chip").forEach((c) => c.addEventListener("click", () => {
      const id = c.dataset.room;
      if (this._roomSel.has(id)) this._roomSel.delete(id); else this._roomSel.add(id);
      this._syncRooms();
    }));
    this.querySelectorAll(".vc-rooms .vc-pass").forEach((b) => b.addEventListener("click", () => { this._passes = +b.dataset.pass; this._syncRooms(); }));
    this._wireScheduleEditor(call);
    q("roomgo")?.addEventListener("click", () => this._cleanRooms(call));
    q("voiceshuffle")?.addEventListener("click", () => call("button", "press", { entity_id: e.voiceshuffle }));
    this._syncRooms();
    this._wireZones();
    this.querySelectorAll(".vc-sen").forEach((c) => c.addEventListener("change", () => call("switch", c.checked ? "turn_on" : "turn_off", { entity_id: c.dataset.ent })));
    this.querySelectorAll(".vc-stime[data-ent]").forEach((t) => t.addEventListener("change", () => call("time", "set_value", { entity_id: t.dataset.ent, time: t.value + ":00" })));
    q("fold")?.addEventListener("click", () => { this._padOpen = !this._padOpen; q("padbox").hidden = !this._padOpen; q("root").classList.toggle("padopen", this._padOpen); });
    q("fold")?.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); q("fold").click(); } });
    // Esc closes whichever dialog is open.
    q("root")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape") return;
      if (q("modal") && !q("modal").hidden) this._showHistView(null);
      if (q("sedit") && !q("sedit").hidden) { q("sedit").hidden = true; this._sedit = null; }
      if (q("confirm") && !q("confirm").hidden) q("confirmno").click();
    });
    q("mclose")?.addEventListener("click", () => this._showHistView(null));
    q("modalbg")?.addEventListener("click", () => this._showHistView(null));
    q("kpis")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".vc-kpi-reset"); if (!btn) return;
      const key = btn.dataset.reset, id = e.buttons[key]; if (!id) return;
      const tt = this._t, labels = { resetmain: tt.brush, resetside: tt.side_brush, resetfilter: tt.filter };
      const part = labels[key] || "";
      this._confirm(tt.reset_confirm.replace("{part}", tt.keep_case ? part : part.toLowerCase()),
        () => call("button", "press", { entity_id: id }));
    });
  }

  // ILIFE Clean schedules: `schedules` sensor rows + a modal editor calling
  // ilife.set_schedule / ilife.delete_schedule.
  _wireScheduleEditor(call) {
    const e = this._ent, q = (s) => this.querySelector(`[data-el="${s}"]`);
    if (!e.tsched || !q("sedit")) return;
    const close = () => { q("sedit").hidden = true; this._sedit = null; };
    q("tschedadd").addEventListener("click", () => this._openSchedule(null));
    q("seditclose").addEventListener("click", close);
    q("seditbg").addEventListener("click", close);
    this.querySelectorAll(".vc-sedays .vc-chip").forEach((c) => c.addEventListener("click", () => {
      const d = +c.dataset.day, days = this._sedit.days;
      if (days.has(d)) days.delete(d); else days.add(d);
      this._syncSchedule();
    }));
    q("setype").querySelectorAll(".vc-pill").forEach((p) => p.addEventListener("click", (ev) => {
      ev.stopPropagation(); this._sedit.type = p.dataset.val; this._syncSchedule();
    }));
    q("serooms").querySelectorAll(".vc-chip").forEach((c) => c.addEventListener("click", () => {
      const r = +c.dataset.room, rooms = this._sedit.rooms;
      if (rooms.has(r)) rooms.delete(r); else rooms.add(r);
      this._syncSchedule();
    }));
    this.querySelectorAll(".vc-sedit .vc-pass").forEach((b) => b.addEventListener("click", () => {
      this._sedit.cycles = +b.dataset.cyc; this._syncSchedule();
    }));
    q("sesave").addEventListener("click", () => {
      const s = this._sedit, time = q("setime").value;
      if (!s || !time || !s.days.size || (s.type === "rooms" && !s.rooms.size)) return;
      const data = { entity_id: e.vacuum, time, days: [...s.days].sort(), cycles: s.cycles,
        rooms: s.type === "rooms" ? [...s.rooms].sort((a, b) => a - b) : [] };
      if (s.slot) data.slot = s.slot; else data.enabled = true;
      call("ilife", "set_schedule", data);
      close();
    });
    q("sedel").addEventListener("click", () => {
      if (this._sedit?.slot) call("ilife", "delete_schedule", { entity_id: e.vacuum, slot: this._sedit.slot });
      close();
    });
  }

  _openSchedule(s) {
    const t = this._t, q = (x) => this.querySelector(`[data-el="${x}"]`);
    this._sedit = s
      ? { slot: s.slot, days: new Set(s.days), type: s.type, rooms: new Set(s.rooms), cycles: s.cycles || 1 }
      : { slot: null, days: new Set(), type: "global", rooms: new Set(), cycles: 1 };
    q("setime").value = s ? s.time : "09:00";
    q("sedittitle").textContent = s ? `${t.edit_schedule} ${s.slot}` : t.new_schedule;
    q("sedel").hidden = !s;
    q("sedit").hidden = false;
    this._syncSchedule();
  }

  _syncSchedule() {
    const s = this._sedit; if (!s) return;
    const q = (x) => this.querySelector(`[data-el="${x}"]`);
    this.querySelectorAll(".vc-sedays .vc-chip").forEach((c) => c.classList.toggle("on", s.days.has(+c.dataset.day)));
    const pills = [...q("setype").querySelectorAll(".vc-pill")];
    const idx = pills.findIndex((p) => p.dataset.val === s.type);
    pills.forEach((p, i) => p.classList.toggle("active", i === idx));
    const thumb = q("setype").querySelector(".vc-thumb");
    if (thumb) thumb.style.transform = `translateX(calc(${Math.max(0, idx)} * 100%))`;
    q("serooms").hidden = s.type !== "rooms";
    q("serooms").querySelectorAll(".vc-chip").forEach((c) => c.classList.toggle("on", s.rooms.has(+c.dataset.room)));
    this.querySelectorAll(".vc-sedit .vc-pass").forEach((b) => b.classList.toggle("on", +b.dataset.cyc === s.cycles));
    q("sesave").disabled = !s.days.size || (s.type === "rooms" && !s.rooms.size);
  }

  _renderSchedules() {
    const hass = this._hass, e = this._ent, t = this._t;
    const list = this.querySelector('[data-el="tschedlist"]');
    if (!e.tsched || !list) return;
    const items = hass.states[e.tsched]?.attributes.schedules || [];
    const sig = JSON.stringify(items) + this._lang;
    if (sig !== this._tschedSig) {
      this._tschedSig = sig;
      list.innerHTML = items.length ? items.map((s) => {
        const days = s.days.length === 7 ? t.every_day : s.days.map((d) => t.dshort[d]).join(", ");
        const what = s.type === "rooms" ? (s.room_names || []).join(", ") : t.whole_home;
        return `<div class="vc-lrow vc-trow${s.enabled ? "" : " off"}" data-slot="${esc(s.slot)}" role="button" tabindex="0">
          <span class="vc-tmeta"><span class="vc-ttime vc-num">${esc(s.time)}</span><span class="vc-tdays">${esc(days)}</span>
            <span class="vc-tsum">${esc(what)} · ${esc(s.cycles)}×</span></span><span></span>
          <label class="vc-switch"><input type="checkbox" class="vc-ten" data-slot="${s.slot}"${s.enabled ? " checked" : ""}><span class="vc-slider"></span></label></div>`;
      }).join("") : `<div class="vc-empty">—</div>`;
      list.querySelectorAll(".vc-trow").forEach((row) => row.addEventListener("click", (ev) => {
        if (ev.target.closest(".vc-switch")) return;
        this._openSchedule(items.find((s) => s.slot === +row.dataset.slot));
      }));
      list.querySelectorAll(".vc-ten").forEach((c) => c.addEventListener("change", () =>
        hass.callService("ilife", "set_schedule", { entity_id: e.vacuum, slot: +c.dataset.slot, enabled: c.checked })));
    }
    const on = items.filter((s) => s.enabled);
    const cnt = this.querySelector('[data-el="tschedcount"]');
    if (cnt) cnt.textContent = `${on.length} ${t.active}`;
    const onDays = new Set(on.flatMap((s) => s.days.map((d) => d + 1)));
    this.querySelectorAll(".blk-sched .vc-daypill").forEach((p) => p.classList.toggle("on", onDays.has(+p.dataset.day)));
  }

  _cleanRooms(call) {
    if (!this._roomSel.size) return;
    call("ilife", "clean_rooms", { entity_id: this._ent.vacuum, rooms: [...this._roomSel].map(Number), passes: this._passes });
    this._roomSel.clear();
    this._syncRooms();
  }

  // Zones: rectangles in map cells (robot frame, y up), drawn over the camera image,
  // kept per vacuum in this browser so a usual zone is there next time.
  _zoneKey() { return "ilife-vacuum-card:zones:" + this._ent.vacuum; }
  _loadZones() {
    if (this._zonesFor === this._ent.vacuum) return;
    const switched = this._zonesFor !== undefined;
    this._zonesFor = this._ent.vacuum;
    this._zones = []; this._zonePasses = 1; this._zonesMap = null;
    if (switched) { this._roomSel = new Set(); this._wantMode = null; }
    try {
      const saved = JSON.parse(localStorage.getItem(this._zoneKey()) || "null");
      if (saved) {
        this._zones = (saved.zones || []).filter((z) => Array.isArray(z) && z.length === 4 && z.every(Number.isFinite)).slice(0, MAX_ZONES);
        this._zonePasses = saved.passes === 2 ? 2 : 1;
        this._zonesMap = saved.map_id ?? null;
        this._wantMode = saved.mode || null;
        if (this._modes.includes(saved.mode)) this._mode = saved.mode;
      }
    } catch (err) { /* no storage: start empty */ }
  }
  _saveZones() {
    try {
      localStorage.setItem(this._zoneKey(), JSON.stringify({ zones: this._zones, passes: this._zonePasses,
        mode: this._wantMode || this._mode, map_id: this._zonesMap }));
    } catch (err) { /* no storage */ }
  }
  // Zones are cells of one map: after the robot re-maps (a new map_id) they point
  // elsewhere, so they are dropped rather than sent.
  _checkZoneMap() {
    const id = this._hass.states[this._ent.map]?.attributes.map_id;
    if (id == null) return;
    if (this._zonesMap != null && this._zonesMap !== id && this._zones.length) this._zones = [];
    if (this._zonesMap !== id) { this._zonesMap = id; this._saveZones(); }
  }

  _wireZones() {
    this._loadZones();
    const q = (s) => this.querySelector(`[data-el="${s}"]`);
    const box = q("zones");
    this.querySelectorAll(".vc-zbar .vc-pass").forEach((b) => b.addEventListener("click", () => {
      this._zonePasses = +b.dataset.zpass; this._saveZones(); this._update();
    }));
    q("zadd")?.addEventListener("click", () => this._addZone());
    const img = q("map");
    // The calibration that belongs to the image on screen: the attributes can run
    // ahead of the image, which is only fetched every 20 s.
    if (img) img.addEventListener("load", () => {
      this._imgCal = zoneCalibration(this._hass.states[this._ent.map]?.attributes);
      this._syncModes();
    });
    if (!box) return;
    box.addEventListener("pointerdown", (ev) => {
      if (this._drag || (ev.pointerType === "mouse" && ev.button !== 0)) return;   // keep the first finger
      if (ev.target.closest(".vc-zdel")) return;    // deleted on click, below
      const zEl = ev.target.closest(".vc-zone");
      if (!zEl) {
        // Draw a new zone by dragging across the map, as in the app.
        if (this._zones.length >= MAX_ZONES || !this._zoneGeo()) return;
        ev.preventDefault();
        const b = box.getBoundingClientRect();
        this._drag = { kind: "draw", i: null, el: null, x: ev.clientX, y: ev.clientY,
          ax: ev.clientX - b.left, ay: ev.clientY - b.top, id: ev.pointerId };
        box.setPointerCapture(ev.pointerId);
        return;
      }
      const i = +zEl.dataset.i;
      ev.preventDefault();
      const r = this._zoneRect(this._zones[i]); if (!r) return;
      this._drag = { i, el: zEl, kind: ev.target.closest(".vc-zrs") ? "size" : "move",
        x: ev.clientX, y: ev.clientY, r, id: ev.pointerId, orig: this._zones[i].slice() };
      zEl.setPointerCapture(ev.pointerId);
    });
    box.addEventListener("click", (ev) => {
      const del = ev.target.closest(".vc-zdel"); if (!del) return;
      this._zones.splice(+del.closest(".vc-zone").dataset.i, 1);
      this._saveZones(); this._update();
    });
    box.addEventListener("pointermove", (ev) => {
      const d = this._drag; if (!d || ev.pointerId !== d.id) return;
      const W = box.clientWidth, H = box.clientHeight, dx = ev.clientX - d.x, dy = ev.clientY - d.y;
      const min = this._zoneMinPx();
      if (d.kind === "draw") {
        const cx = Math.max(0, Math.min(W, d.ax + dx)), cy = Math.max(0, Math.min(H, d.ay + dy));
        const r = { l: Math.min(d.ax, cx), t: Math.min(d.ay, cy), w: Math.abs(cx - d.ax), h: Math.abs(cy - d.ay) };
        if (d.i === null) {
          if (Math.max(r.w, r.h) < 8) return;         // a tap, not a drag yet
          const z = this._rectZone(r); if (!z) return;
          d.i = this._zones.length;
          this._zones.push(z);
          this._renderZones();
          d.el = box.querySelector(`.vc-zone[data-i="${d.i}"]`);
        }
        const z = this._rectZone(r); if (!z) return;
        this._zones[d.i] = z;
        this._placeZone(d.el, z);
        return;
      }
      let { l, t, w, h } = d.r;
      if (d.kind === "move") {
        l = Math.max(0, Math.min(W - w, l + dx)); t = Math.max(0, Math.min(H - h, t + dy));
      } else {
        w = Math.min(W - l, Math.max(min, w + dx)); h = Math.min(H - t, Math.max(min, h + dy));
      }
      const z = this._rectZone({ l, t, w, h }); if (!z) return;
      this._zones[d.i] = z;
      this._placeZone(d.el, z);
    });
    const end = (ev) => {
      const d = this._drag; if (!d || ev.pointerId !== d.id) return;
      this._drag = null;
      if (ev.type === "pointercancel") {
        // The system took the gesture over (a back swipe...): undo it.
        if (d.kind === "draw") { if (d.i !== null) this._zones.splice(d.i, 1); }
        else this._zones[d.i] = d.orig;
        this._update(); return;
      }
      // A drawn zone smaller than the minimum grows to it from its first corner.
      if (d.kind === "draw" && d.i !== null) {
        const r = this._zoneRect(this._zones[d.i]), min = this._zoneMinPx();
        if (r && (r.w < min || r.h < min)) {
          r.w = Math.max(r.w, min); r.h = Math.max(r.h, min);
          r.l = Math.min(r.l, box.clientWidth - r.w); r.t = Math.min(r.t, box.clientHeight - r.h);
          this._zones[d.i] = this._rectZone(r);
        }
      }
      this._saveZones(); this._update();
    };
    box.addEventListener("pointerup", end);
    box.addEventListener("pointercancel", end);
    box.addEventListener("lostpointercapture", end);
  }

  // The overlay's geometry: image pixels -> overlay pixels is a plain scale.
  // `object-fit: contain` can letterbox the picture inside the element (the
  // full-page layout sizes it by height): the overlay covers the picture only.
  _zoneGeo() {
    const img = this.querySelector('[data-el="map"]');
    const cal = this._imgCal;
    if (!img || img.hidden || !img.naturalWidth || !img.offsetWidth || !cal) return null;
    const k = Math.min(img.offsetWidth / img.naturalWidth, img.offsetHeight / img.naturalHeight);
    const w = img.naturalWidth * k, h = img.naturalHeight * k;
    return { img, cal, k, left: img.offsetLeft + (img.offsetWidth - w) / 2,
      top: img.offsetTop + (img.offsetHeight - h) / 2, w, h };
  }
  _zoneMinPx() {
    const g = this._zoneGeo(); if (!g) return 20;
    const res = Number(this._hass.states[this._ent.map]?.attributes.resolution_cm) || 5;
    const a = g.cal.toPx(0, 0), b = g.cal.toPx(50 / res, 0);   // 0.5 m
    return Math.max(16, Math.abs(b[0] - a[0]) * g.k);
  }
  _zoneRect(z) {
    const g = this._zoneGeo(); if (!g) return null;
    const a = g.cal.toPx(z[0], z[1]), b = g.cal.toPx(z[2], z[3]);
    const l = Math.min(a[0], b[0]) * g.k, t = Math.min(a[1], b[1]) * g.k;
    return { l, t, w: Math.abs(b[0] - a[0]) * g.k, h: Math.abs(b[1] - a[1]) * g.k };
  }
  _rectZone(r) {
    const g = this._zoneGeo(); if (!g) return null;
    const a = g.cal.toCell(r.l / g.k, r.t / g.k), b = g.cal.toCell((r.l + r.w) / g.k, (r.t + r.h) / g.k);
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  }
  _placeZone(el, z) {
    const r = this._zoneRect(z); if (!r) return;
    Object.assign(el.style, { left: r.l + "px", top: r.t + "px", width: r.w + "px", height: r.h + "px" });
    const res = Number(this._hass.states[this._ent.map]?.attributes.resolution_cm) || 5;
    const m = (v) => (Math.abs(v) * res / 100).toFixed(1);
    el.querySelector(".vc-zsize").textContent = `${m(z[2] - z[0])} × ${m(z[3] - z[1])} ${this._t.m}`;
  }

  _addZone() {
    const g = this._zoneGeo(); if (!g || this._zones.length >= MAX_ZONES) return;
    const res = Number(this._hass.states[this._ent.map]?.attributes.resolution_cm) || 5;
    const side = 200 / res, n = this._zones.length;          // 2 m, each next one offset
    const [cx, cy] = g.cal.toCell(g.img.naturalWidth / 2, g.img.naturalHeight / 2);
    const x = cx - side / 2 + n * side / 4, y = cy - side / 2 - n * side / 4;
    this._zones.push([x, y, x + side, y + side]);
    this._saveZones();
    this._update();
  }

  _layoutZones() {
    const box = this.querySelector('[data-el="zones"]');
    if (!box || this._drag) return;
    const g = this._mode === "zones" ? this._zoneGeo() : null;
    box.hidden = !g;
    if (!g) return;
    Object.assign(box.style, { left: g.left + "px", top: g.top + "px", width: g.w + "px", height: g.h + "px" });
    // New elements only when the count changed: a hass update must not replace the
    // node under a finger.
    if (box.children.length !== this._zones.length) this._renderZones();
    else box.querySelectorAll(".vc-zone").forEach((el) => this._placeZone(el, this._zones[+el.dataset.i]));
  }

  _renderZones() {
    const box = this.querySelector('[data-el="zones"]'); if (!box) return;
    box.innerHTML = this._zones.map((z, i) => `<div class="vc-zone" data-i="${i}">
      <button class="vc-zbtn vc-zdel" aria-label="${this._t.delete}"><ha-icon icon="mdi:close"></ha-icon></button>
      <span class="vc-zbtn vc-zrs"><ha-icon icon="mdi:arrow-top-left-bottom-right"></ha-icon></span>
      <span class="vc-zsize vc-num"></span></div>`).join("");
    box.querySelectorAll(".vc-zone").forEach((el) => this._placeZone(el, this._zones[+el.dataset.i]));
  }

  // The mode switch, the blocks it shows, and what the start button says.
  _syncModes() {
    const q = (s) => this.querySelector(`[data-el="${s}"]`), t = this._t;
    const hasControls = !!q("cta"), mode = this._mode;
    this._setActive("cmode", mode);
    q("root")?.classList.toggle("zoning", mode === "zones");
    if (q("rooms") && hasControls) q("rooms").hidden = mode !== "rooms";
    if (q("zbar")) {
      this._checkZoneMap();
      const geo = this._zoneGeo();
      q("zbar").hidden = mode !== "zones";
      q("zadd").disabled = this._zones.length >= MAX_ZONES || !geo;
      q("zhint").textContent = geo ? t.zone_hint : t.no_map_yet;
      q("zhint").hidden = !!geo && this._zones.length > 0;
      this.querySelectorAll(".vc-zbar .vc-pass").forEach((b) => b.classList.toggle("on", +b.dataset.zpass === this._zonePasses));
    }
    this._layoutZones();
    const cta = q("cta"); if (!cta) return;
    const st = this._hass.states[this._ent.vacuum]?.state;
    let txt = t.start, ic = "mdi:play", off = false;
    if (st === "cleaning") { txt = t.pause; ic = "mdi:pause"; }
    else if (st === "paused") { txt = t.resume; ic = "mdi:play"; }
    else if (mode === "rooms") {
      const n = (this._roomSel || new Set()).size;
      txt = t.clean_rooms + (n ? ` (${n}) · ${this._passes}×` : ""); ic = "mdi:broom"; off = !n;
    } else if (mode === "zones") {
      const n = this._zones.length;
      txt = t.clean_zones + (n ? ` (${n}) · ${this._zonePasses}×` : ""); ic = "mdi:select-drag"; off = !n;
    }
    q("ctatxt").textContent = txt; q("ctaicon").setAttribute("icon", ic);
    cta.disabled = off;
  }

  _syncRooms() {
    const sel = this._roomSel || new Set();
    this.querySelectorAll(".vc-rooms .vc-chip").forEach((c) => c.classList.toggle("on", sel.has(c.dataset.room)));
    this.querySelectorAll(".vc-rooms .vc-pass").forEach((b) => b.classList.toggle("on", +b.dataset.pass === this._passes));
    const go = this.querySelector('[data-el="roomgo"]');
    if (go) {
      go.disabled = !sel.size;
      this.querySelector('[data-el="roomgotxt"]').textContent =
        this._t.clean_rooms + (sel.size ? ` (${sel.size}) · ${this._passes}×` : "");
    }
    if (this._zones) this._syncModes();
  }

  _confirm(msg, onOk) {
    const modal = this.querySelector('[data-el="confirm"]');
    if (!modal) { if (onOk) onOk(); return; }
    this.querySelector('[data-el="confirmmsg"]').textContent = msg;
    modal.hidden = false;
    const yes = this.querySelector('[data-el="confirmyes"]');
    const no = this.querySelector('[data-el="confirmno"]');
    const bg = this.querySelector('[data-el="confirmbg"]');
    const cleanup = () => {
      modal.hidden = true;
      yes.removeEventListener("click", onYes);
      no.removeEventListener("click", onNo);
      bg.removeEventListener("click", onNo);
    };
    const onYes = () => { cleanup(); if (onOk) onOk(); };
    const onNo = () => cleanup();
    yes.addEventListener("click", onYes);
    no.addEventListener("click", onNo);
    bg.addEventListener("click", onNo);
  }

  _startMapTimer() { if (this._mapTimer) clearInterval(this._mapTimer); this._refreshMap(); this._mapTimer = setInterval(() => this._refreshMap(), 20000); }
  _refreshMap() {
    const e = this._ent; if (!e || !e.map) return;
    const img = this.querySelector('[data-el="map"]'); const st = this._hass.states[e.map];
    const pic = st && st.attributes.entity_picture; if (!img || !pic) return;
    // Keep fetching while the camera is unavailable: the ILIFEHOME camera renders on
    // request, and only becomes available once it has. What a failed fetch shows is
    // the "no map" placeholder, not a broken image (#30).
    if (!img.onerror) {
      img.onerror = () => { if (this._imgOk !== false) { this._imgOk = false; this._update(); } };
      img.onload = () => { if (this._imgOk !== true) { this._imgOk = true; this._update(); } };
    }
    img.src = this._hass.hassUrl(pic) + (pic.includes("?") ? "&" : "?") + "t=" + Date.now();
  }

  _showHistView(clean) {
    const modal = this.querySelector('[data-el="modal"]'); if (!modal) return;
    if (!clean) { modal.hidden = true; return; }
    const dec = decodeCleanMap(clean.map || clean.thumb);
    if (!dec || !dec.cells.length) { modal.hidden = true; return; }
    const mw = Math.min((window.innerWidth || 600) * 0.8, 600), mh = (window.innerHeight || 700) * 0.6;
    drawMapCells(this.querySelector('[data-el="mcanvas"]'), dec.cells, mw, mh, clean.path);
    const cap = this.querySelector('[data-el="mcap"]');
    if (cap) cap.textContent = this._fmtWhen(clean.start, true);
    const stats = this.querySelector('[data-el="mstats"]'), t = this._t;
    if (stats) stats.innerHTML =
      `<div class="s"><div class="v">${clean.area ?? "?"}</div><div class="l">${t.m2_cleaned}</div></div>` +
      `<div class="s"><div class="v">${clean.duration ?? "?"}</div><div class="l">${t.minutes}</div></div>`;
    modal.hidden = false;
  }

  _setActive(key, val) {
    const seg = this.querySelector(`.vc-seg[data-seg="${key}"]`); if (!seg) return;
    const pills = [...seg.querySelectorAll(".vc-pill")];
    let idx = -1;
    pills.forEach((p, i) => { const on = p.dataset.val === val; p.classList.toggle("active", on); if (on) idx = i; });
    const thumb = seg.querySelector(".vc-thumb");
    if (thumb) { if (idx < 0) thumb.classList.add("hidden"); else { thumb.classList.remove("hidden"); thumb.style.transform = `translateX(calc(${idx} * 100%))`; } }
  }

  _fmtWhen(sec, withDate) {
    if (!sec) return "—";
    const t = this._t, d = new Date(sec * 1000), now = new Date();
    const yest = new Date(now); yest.setDate(now.getDate() - 1);
    let hm, day;
    try {
      hm = d.toLocaleTimeString(this._timeLocale(), this._timeOpts());
      day = d.toLocaleDateString(this._locale(), { weekday: "short", day: "numeric", month: "short" });
    } catch (err) {  // a language tag the browser rejects
      hm = d.toLocaleTimeString(t.locale, this._timeOpts());
      day = d.toLocaleDateString(t.locale, { weekday: "short", day: "numeric", month: "short" });
    }
    if (d.toDateString() === now.toDateString()) return `${t.today} ${hm}`;
    if (d.toDateString() === yest.toDateString()) return `${t.yesterday} ${hm}`;
    return day + (withDate ? " " + hm : "");
  }

  _kpi(icon, val, label, gauge, resetKey) {
    return `<div class="vc-kpi">${resetKey ? `<button class="vc-kpi-reset" data-reset="${resetKey}" title="${this._t.reset}" aria-label="${this._t.reset}"><ha-icon icon="mdi:restore"></ha-icon></button>` : ""}<div class="ic"><ha-icon icon="${icon}"></ha-icon></div>
      <div class="v vc-num">${val}</div><div class="l">${label}</div>
      ${gauge != null ? `<div class="vc-gauge"><i style="width:${Math.max(0, Math.min(100, gauge))}%;${gauge <= 15 ? "background:var(--warning-color,#f9a825)" : ""}"></i></div>` : ""}</div>`;
  }

  _update() {
    if (!this._built || !this._ent || !this._ent.vacuum) return;
    const hass = this._hass, e = this._ent, t = this._t;
    const vs = hass.states[e.vacuum]; if (!vs) return;
    const q = (s) => this.querySelector(`[data-el="${s}"]`);
    const root = q("root");
    const num = (id) => { const s = hass.states[id]; const v = s ? Number(s.state) : NaN; return isFinite(v) ? v : null; };
    // A sensor's value in the card's unit; one it does not know is taken as is.
    const inUnit = (id, per) => {
      const v = num(id);
      const factor = per[hass.states[id]?.attributes.unit_of_measurement];
      return v == null || factor == null ? v : v * factor;
    };

    const online = e.online ? hass.states[e.online]?.state === "on" : true;
    root.classList.toggle("online", online);
    root.classList.toggle("offline", e.online && !online);
    root.classList.toggle("cleaning", vs.state === "cleaning");

    if (q("name")) {
      q("name").textContent = vs.attributes.friendly_name || "ILIFE";
      const stTxt = t.st[vs.state] || vs.state;
      q("state").textContent = (!online && e.online)
        ? (["docked", "idle", "paused"].includes(vs.state) ? `${stTxt} · ${t.sleeping}` : t.offline)
        : stTxt;
    }

    const bv = e.battery ? num(e.battery) : null;
    if (q("batt")) {
      if (bv != null) {
        q("battval").textContent = Math.round(bv) + "%";
        const lvl = Math.round(bv / 10) * 10;
        q("batticon").setAttribute("icon", lvl >= 100 ? "mdi:battery" : lvl <= 0 ? "mdi:battery-outline" : `mdi:battery-${lvl}`);
        q("batt").style.color = bv <= 15 ? "var(--error-color,#db4437)" : bv <= 30 ? "var(--warning-color,#f9a825)" : "var(--secondary-text-color)";
        q("battbar").style.width = Math.max(2, Math.min(100, bv)) + "%";
        q("batt").hidden = false;
      } else q("batt").hidden = true;
    }

    if (q("badgetxt")) {
      const mapAttrs = e.map ? hass.states[e.map]?.attributes || {} : {};
      // ILIFE Clean: `map_path` says whether the path on the map belongs to this run
      // ("live"), is left out mid-run ("hidden", or "waiting" for a first map), or
      // is the last one ("last_run").
      const livePath = mapAttrs.map_source === "realtime" || mapAttrs.map_path === "live";
      q("badgetxt").textContent = (!online && e.online)
        ? t.sleeping
        : vs.state !== "cleaning" ? t.last_run
        : livePath ? t.live
        : ["hidden", "waiting"].includes(mapAttrs.map_path) ? t.floor_plan
        : t.last_run;
    }

    if (q("scrim")) {
      if (vs.state === "cleaning") {
        const fs = vs.attributes.fan_speed
          ? (hass.formatEntityAttributeValue ? hass.formatEntityAttributeValue(vs, "fan_speed") : vs.attributes.fan_speed) : "";
        const ct = e.curtime ? num(e.curtime) : null, ca = e.curarea ? num(e.curarea) : null;
        const parts = [];
        if (ct != null) parts.push(`<b>${ct}</b> ${t.min.trim()}`);
        if (ca != null) parts.push(`<b>${ca}</b> m²`);
        if (bv != null) parts.push(`<b>${Math.round(bv)}</b>% ${t.battery}`);
        if (fs) parts.push(fs);
        q("scrim").innerHTML = parts.map((p, i) => `<span>${i ? "· " : ""}${p}</span>`).join("");
        q("scrim").hidden = false;
      } else q("scrim").hidden = true;
    }



    this._setActive("fan", vs.attributes.fan_speed);
    if (e.water) this._setActive("water", hass.states[e.water]?.state);
    if (e.mode) this._setActive("mode", hass.states[e.mode]?.state);
    if (e.efficiency) this._setActive("eff", hass.states[e.efficiency]?.state);
    if (e.program) this._setActive("prog", hass.states[e.program]?.state);
    if (e.voice) this._setActive("voice", hass.states[e.voice]?.state);

    this.querySelectorAll(".vc-tog").forEach((c) => {
      if (document.activeElement !== c) c.checked = hass.states[c.dataset.ent]?.state === "on";
    });
    if (e.volume && q("volume") && document.activeElement !== q("volume")) {
      const v = Number(hass.states[e.volume]?.state);
      if (Number.isFinite(v)) { q("volume").value = v; q("volval").textContent = v + "%"; }
    }
    if (q("problem")) {
      const ps = e.problem && hass.states[e.problem];
      const faults = ps && ps.state === "on" ? (ps.attributes.faults || []) : [];
      q("problem").hidden = !faults.length;
      q("problemtxt").textContent = faults.map((f) => (t.faults && t.faults[f]) || FAULTS_EN[f] || f.replace(/_fault$/, "").replace(/_/g, " ")).join(", ");
    }

    const cleans = (e.history && hass.states[e.history]?.attributes.cleans) || [];
    const sensorCycles = e.totalcount ? num(e.totalcount) : null;
    // The area and duration sensors have device classes, so their display unit can
    // be changed (hours, ft²...): convert back to the m² and minutes shown here.
    const sensorArea = e.totalarea ? inUnit(e.totalarea, M2_PER) : null;
    const sensorMinutes = e.totaltime ? inUnit(e.totaltime, MIN_PER) : null;
    const attrNum = (key) => {
      const value = Number(vs.attributes[key]);
      return Number.isFinite(value) ? value : null;
    };
    const directCycles = attrNum("total_clean_count");
    const directArea = attrNum("total_clean_area");
    const directMinutes = attrNum("total_clean_time");
    const cycles = sensorCycles != null
      ? sensorCycles
      : (directCycles != null ? directCycles : cleans.length);

    // Hero map: live camera while cleaning, otherwise the last completed clean's full map
    const img = q("map"), hero = q("heromap");
    if (img && hero) {
      let usedHero = false;
      if (vs.state !== "cleaning" && this._mode !== "zones") {
        const last = cleans.find((c) => c.map);
        const dec = last && decodeCleanMap(last.map);
        if (dec && dec.cells.length) {
          if (this._heroSrc !== last.map) { this._heroSrc = last.map; this._heroCells = dec.cells; }
          hero.hidden = false; img.hidden = true; usedHero = true;
          this._fitHero();
          if (q("badgetxt") && online) q("badgetxt").textContent = t.last_run;
        }
      }
      // The last fetch decides; before there is one, the camera's own state does.
      const cam = hass.states[e.map];
      const noMap = !usedHero && (this._imgOk === false
        || (this._imgOk !== true && (!cam || cam.state === "unavailable")));
      if (!usedHero) { this._heroCells = null; hero.hidden = true; img.hidden = noMap; }
      if (q("nomap")) q("nomap").hidden = !noMap;
    }
    if (e.map) {
      const ma = hass.states[e.map]?.attributes || {};
      const calSig = JSON.stringify([ma.calibration_points, ma.map_id]);
      if (this._calSig !== undefined && calSig !== this._calSig && ma.calibration_points) this._refreshMap();
      this._calSig = calSig;
    }
    if (this._zones) this._syncModes();
    const totArea = sensorArea != null
      ? sensorArea
      : (directArea != null
        ? directArea
        : cleans.reduce((s, c) => s + (Number(c.area) || 0), 0));
    const totMin = sensorMinutes != null
      ? sensorMinutes
      : (directMinutes != null
        ? directMinutes
        : cleans.reduce((s, c) => s + (Number(c.duration) || 0), 0));
    const fmtDur = (minutes) => { const m = Math.round(minutes); return m >= 60 ? Math.floor(m / 60) + t.h.trimEnd() + (m % 60 ? (t.h.endsWith(" ") ? " " : "") + String(m % 60).padStart(2, "0") : "") : m + t.min; };
    const brush = e.brush ? num(e.brush) : null, side = e.side ? num(e.side) : null, filt = e.filter ? num(e.filter) : null;
    if (q("kpis")) {
      let k = "";
      if (this._has("overview")) k += this._kpi("mdi:counter", cycles, t.cycles) +
        this._kpi("mdi:ruler-square", totArea.toFixed(1) + " m²", t.area) +
        this._kpi("mdi:timer-outline", fmtDur(totMin), t.total_time);
      if (this._has("consumables")) {
        if (brush != null) k += this._kpi("mdi:brush", Math.round(brush) + "%", t.brush, brush, e.buttons.resetmain ? "resetmain" : null);
        if (side != null) k += this._kpi("mdi:brush-variant", Math.round(side) + "%", t.side_brush, side, e.buttons.resetside ? "resetside" : null);
        if (filt != null) k += this._kpi("mdi:air-filter", Math.round(filt) + "%", t.filter, filt, e.buttons.resetfilter ? "resetfilter" : null);
      }
      q("kpis").innerHTML = k;
    }
    if (q("histcount")) q("histcount").textContent = cycles ? `${cycles} ${this._plural(cycles)}` : "";
    const histSig = cleans.slice(0, 12).map((c) => `${c.record_id ?? c.start}:${c.area}:${c.duration}`).join() + this._lang;
    if (q("hist") && histSig !== this._histSig) {
      this._histSig = histSig;
      const maxA = Math.max(1, ...cleans.map((c) => Number(c.area) || 0));
      q("hist").innerHTML = cleans.length
        ? cleans.slice(0, 12).map((c, i) => `<div class="vc-hrow" data-idx="${i}" role="button" tabindex="0">
            <span class="vc-hthumb"></span>
            <span class="vc-hmeta"><div class="vc-hwhen">${this._fmtWhen(c.start)}</div>
              <div class="vc-hsub"><span style="display:inline-block;width:${Math.round((Number(c.area) || 0) / maxA * 100)}%;max-width:60px;height:3px;border-radius:2px;background:color-mix(in srgb,var(--primary-color) 60%,transparent);vertical-align:middle"></span></div></span>
            <span class="vc-harea vc-num">${esc(c.area ?? "?")} m² · ${esc(c.duration ?? "?")} ${t.min.trim()}</span>
            <ha-icon class="vc-hchev" icon="mdi:chevron-right"></ha-icon></div>`).join("")
        : `<div class="vc-empty">${t.no_history}</div>`;
      q("hist").querySelectorAll(".vc-hrow").forEach((row) => {
        const c = cleans[Number(row.dataset.idx)];
        const th = row.querySelector(".vc-hthumb");
        // ILIFE Clean sends `thumb` (same format) instead of `map`, so its rows get a
        // thumbnail without the hero map switching away from the camera's render.
        const dec = c && decodeCleanMap(c.map || c.thumb);
        if (dec && dec.cells.length) { const cv = document.createElement("canvas"); th.innerHTML = ""; th.appendChild(cv); drawMapCells(cv, dec.cells, 34, 34); }
        else th.innerHTML = `<ha-icon icon="mdi:broom" style="--mdc-icon-size:16px;color:var(--secondary-text-color)"></ha-icon>`;
        row.addEventListener("click", () => { if (c && (c.map || c.thumb)) this._showHistView(c); });
        row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); row.click(); } });
      });
    }

    if (e.tsched) this._renderSchedules();
    else {
      const onDays = [];
      for (let n = 1; n <= 7; n++) { const s = e.schedules[n]; if (s && s.enable && hass.states[s.enable]?.state === "on") onDays.push(n); }
      if (q("schedcount")) q("schedcount").textContent = onDays.length + " " + t.active;
      this.querySelectorAll(".vc-daypill").forEach((p) => p.classList.toggle("on", onDays.includes(Number(p.dataset.day))));
    }
    this.querySelectorAll(".vc-sen").forEach((c) => { const s = hass.states[c.dataset.ent]; if (s && document.activeElement !== c) c.checked = s.state === "on"; });
    this.querySelectorAll(".vc-stime[data-ent]").forEach((t2) => { const s = hass.states[t2.dataset.ent]; if (s && s.state && s.state.length >= 5 && document.activeElement !== t2) t2.value = s.state.slice(0, 5); });
  }

  connectedCallback() {
    if (!this._built) return;
    if (!this._mapTimer) this._startMapTimer();
    this._observeWidth();
  }
  disconnectedCallback() {
    if (this._mapTimer) clearInterval(this._mapTimer);
    this._mapTimer = null;
    if (this._ro) this._ro.disconnect();
    if (this._roMap) this._roMap.disconnect();
    if (this._fitRaf && typeof cancelAnimationFrame === "function") cancelAnimationFrame(this._fitRaf);
    this._fitRaf = 0;
    this._drag = null;
  }
}
if (!customElements.get("ilife-vacuum-card")) customElements.define("ilife-vacuum-card", IlifeVacuumCard);

// Visual editor built on the native <ha-form> selector, so adding the card is a
// modern point-and-click flow (pick the vacuum and the blocks; the rest is auto-detected).
const editorSchema = (t) => [
  { name: "entity", selector: { entity: { domain: "vacuum" } } },
  { name: "show", selector: { select: { multiple: true, mode: "list",
    options: BLOCKS.map((b) => ({ value: b, label: (t.blocks || T.en.blocks)[b] })) } } },
];
class IlifeVacuumCardEditor extends HTMLElement {
  setConfig(config) { this._config = Object.assign({}, config); this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass) return;
    const t = T[cardLang(this._hass)] || T.en;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const config = Object.assign({}, ev.detail.value);
        // Every block ticked is the default: keep `show` out of the YAML then. None
        // ticked would be an empty card, so it means every block too.
        const show = config.show;
        if (Array.isArray(show) && (!show.length || BLOCKS.every((b) => show.includes(b)))) delete config.show;
        else if (Array.isArray(show)) config.show = BLOCKS.filter((b) => show.includes(b));
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.computeLabel = (s) => (s.name === "entity" ? t.editor_entity : s.name === "show" ? t.editor_show : s.name);
    this._form.hass = this._hass;
    this._form.schema = editorSchema(t);
    // No `show` means everything, so the editor ticks every block for it.
    const show = this._config.show;
    this._form.data = Object.assign({}, this._config,
      { show: typeof show === "string" ? show.split(",").map((x) => x.trim()) : (show || BLOCKS) });
  }
}
if (!customElements.get("ilife-vacuum-card-editor")) customElements.define("ilife-vacuum-card-editor", IlifeVacuumCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({ type: "ilife-vacuum-card", name: "ILIFE Vacuum Card",
  description: "All-in-one card for the ILIFE vacuum (map, controls, schedules, clickable history); `show` picks the blocks.", preview: true });
console.info(`%c ILIFE-VACUUM-CARD %c ${new URL(import.meta.url).searchParams.get("v") || "dev"} loaded `, "color:#fff;background:#7cadff;border-radius:3px 0 0 3px;padding:2px", "background:#333;color:#fff;border-radius:0 3px 3px 0;padding:2px");
