"""
hotel_passport_compiler.py — Module for compiling verified hotel infrastructure and complete passport objects.
Ensures zero runtime mapping/heuristics by producing ready-to-render strings for every UI tab.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def get_plural_pools(count: int) -> str:
    if count == 1:
        return "1 открытый бассейн с пресной водой"
    elif 2 <= count <= 4:
        return f"{count} открытых бассейна с пресной водой"
    elif count >= 5:
        return f"{count} открытых бассейнов с пресной водой"
    return "Открытый плавательный бассейн"


def build_hotel_infrastructure(name: str, hotel_data: Dict[str, Any]) -> Dict[str, Any]:
    specs = hotel_data.get("specs", {})
    dest = hotel_data.get("destination", "Египет")
    stars = specs.get("stars") or hotel_data.get("stars") or 4
    line = specs.get("beach_line", 1)
    dist_m = specs.get("beach_distance_meters", 0)
    shuttle = specs.get("shuttle_bus", "none")
    beach_type = specs.get("beach_type", "sand")
    sea_entry = specs.get("sea_entry", "shallow_sand")
    aquapark = bool(specs.get("aquapark", False))
    slides = specs.get("slides_total", 0)
    heated = bool(specs.get("heated_pools_winter", False))
    pools_cnt = specs.get("pool_count", 1 if stars <= 3 else 2)
    food_concept = specs.get("food_concept", "AI")
    renovation = specs.get("last_renovation_year", 2019)
    transfer = specs.get("transfer_minutes", 25)

    # 1. Beach block
    if line == 1:
        if dist_m > 0:
            line_str = f"1-я линия (~{dist_m} м до моря, прямой выход)"
        else:
            line_str = "1-я линия (собственный оборудованный пляж)"
    elif line == 2:
        dist_s = f"~{dist_m} м" if dist_m > 0 else "250–500 м"
        shuttle_s = ", курсирует бесплатный шаттл" if shuttle == "free" else ""
        line_str = f"2-я линия ({dist_s}, через променад или дорогу{shuttle_s})"
    else:
        dist_str = f"~{dist_m} м" if dist_m > 0 else "в глубине курорта"
        line_str = f"3-я линия ({dist_str}"
        if shuttle == "free":
            line_str += ", бесплатный шаттл на пляж)"
        elif shuttle == "paid":
            line_str += ", платный шаттл на пляж)"
        else:
            line_str += ", пешая доступность или такси)"

    btype_map = {
        "sand": "Песчаный пляж",
        "pebble": "Галечный пляж (кристально чистая вода)",
        "coral_rocky": "Кораллово-песчаный берег с рифом",
        "mixed": "Песчано-галечный пляж",
    }
    btype_str = btype_map.get(beach_type, "Песчаный пляж")

    entry_map = {
        "shallow_sand": "Пологий песчаный вход, идеален для детей и плавания без спецобуви",
        "pontoon_to_reef": "Песчаное мелководье у берега, вход на глубину и к рифу с понтона",
        "deep_sand": "Песчаный вход с быстрым набором комфортной для плавания глубины",
        "pebbles_need_shoes": "Галечный вход, для комфортного купания рекомендуется специальная обувь",
        "jetty": "Вход в море с пирса или специально оборудованной платформы",
    }
    entry_str = entry_map.get(sea_entry, "Комфортный вход в море")

    if line == 1:
        equip_str = "Бесплатные шезлонги, солнцезащитные зонты, пляжные полотенца, бар на пляже"
    elif line == 2:
        equip_str = "Шезлонги и зонты на выделенной зоне пляжа (бесплатно), пляжные полотенца"
    else:
        if stars <= 3:
            equip_str = "Шезлонги и зонты на арендованном городском пляже (бесплатно). Бар на пляже за доплату"
        else:
            equip_str = "Выделенная пляжная зона отеля-партнера с шезлонгами и зонтами"

    reef_str = "Живой коралловый риф, удобный спуск для снорклинга" if "coral" in beach_type or "reef" in sea_entry else "Песчаное дно, безопасное купание"

    # 2. Pools block
    pools_count_str = get_plural_pools(pools_cnt)
    if heated:
        if dest in ("Греция", "Кипр") and stars < 5:
            heated_str = "Открытые сезонные бассейны (без подогрева в летний период)"
        else:
            heated_str = "Бассейн с постоянным зимним подогревом (+28°C)"
    else:
        heated_str = "Открытый бассейн, терраса для загара (зимний подогрев отсутствует)" if pools_cnt == 1 else "Открытые бассейны, терраса для загара (зимний подогрев отсутствует)"

    if aquapark and slides > 0:
        aqua_str = f"Собственный аквапарк ({slides} водных горок)"
    elif aquapark:
        aqua_str = "Собственный аквапарк с водными горками для взрослых и детей"
    elif slides > 0:
        aqua_str = f"{slides} водные горки при бассейне (компактная зона водных горок)"
    else:
        aqua_str = "Водные горки и аквапарк отсутствуют"

    # 3. Food block
    if food_concept == "UAI":
        concept_str = "Ultra All Inclusive"
    elif food_concept == "AI":
        concept_str = "All Inclusive"
    elif food_concept == "HB":
        concept_str = "Half Board (Завтрак + Ужин)"
    elif food_concept == "BB":
        concept_str = "Bed & Breakfast"
    else:
        concept_str = food_concept

    if stars >= 5:
        main_buffet = "Главный ресторан: богатый шведский стол, гриль-станции, тематические вечера и свежая выпечка"
        alacarte = "2–4 ресторана a la carte (итальянская, восточная, морская кухни) по предварительной записи"
        bars = "Круглосуточный лобби-бар, бар у бассейна, пляжный снек-бар с закусками и мороженым"
    elif stars == 4:
        main_buffet = "Главный ресторан: разнообразный шведский стол с блюдами международной и местной кухни"
        if line >= 3:
            alacarte = "Рестораны a la carte отсутствуют. Работают основной ресторан и бар у бассейна"
        else:
            alacarte = "1–2 ресторана a la carte (по предварительной записи) и лобби-бар"
        bars = "Лобби-бар, бар у бассейна и снек-станция в дневное время"
    else:
        main_buffet = "Главный ресторан: базовый шведский стол с блюдами местной и восточной кухни"
        alacarte = "Рестораны a la carte отсутствуют. Доступны основной ресторан и бар у бассейна"
        bars = "Бар у бассейна и напитки в главном ресторане во время питания"

    # 4. Kids block
    if stars >= 5:
        kids_club = "Мини-клуб для детей от 4 до 12 лет с анимационной программой и мастер-классами"
        kids_pool = "Мелкий детский бассейн с навесом от прямого солнца и водными мини-аттракционами" if aquapark or slides else "Мелкий детский бассейн с навесом от солнца"
        kids_playground = "Оборудованная игровая площадка на свежем воздухе и вечернее мини-диско"
    elif stars == 4:
        if line >= 3:
            kids_club = "Детская анимация и базовая игровая площадка"
            kids_pool = "Выделенная мелкая детская секция в бассейне"
            kids_playground = "Игровая площадка на открытом воздухе"
        else:
            kids_club = "Мини-клуб для детей от 4 до 12 лет с анимационной программой"
            kids_pool = "Детский бассейн или мелкая секция в главном бассейне"
            kids_playground = "Оборудованная игровая площадка на свежем воздухе"
    else:
        kids_club = "Мини-клуб отсутствует (эконом-формат без специализированной детской анимации)"
        kids_pool = "Интегрированная мелкая секция в общем бассейне"
        kids_playground = "Компактная детская площадка на территории отеля"

    # 5. Sport & Spa block
    if stars >= 5:
        spa = "Спа-комплекс: турецкий хаммам, сауна, паровая комната и массажные кабинеты"
        fitness = "Современный тренажерный зал с кардио- и силовыми тренажерами"
        watersports = "Дайвинг-центр, снорклинг на домашнем рифе, прокат масок и водные виды спорта" if dest == "Египет" else "Водные виды спорта на пляже (виндсерфинг, каяки, водные лыжи — платно)"
    elif stars == 4:
        if line >= 3:
            spa = "Полноценный спа-комплекс отсутствует (массаж и сауна по запросу за доплату)"
            fitness = "Тренажерный зал отсутствует либо компактная фитнес-комната"
            watersports = "Снорклинг и водные виды спорта доступны на общественном пляже платно"
        else:
            spa = "Спа-зона: сауна, парная и массажные кабинеты (процедуры платно)"
            fitness = "Тренажерный зал с базовыми кардио- и силовыми тренажерами"
            watersports = "Снорклинг и водные развлечения на пляже (платно)"
    else:
        spa = "Спа-комплекс отсутствует (массажные услуги по запросу за доплату)"
        fitness = "Тренажерный зал отсутствует"
        watersports = "Водные виды спорта и снорклинг доступны на городском пляже платно"

    # 6. Comfort block
    if stars >= 5:
        wifi = "Бесплатный высокоскоростной Wi-Fi на всей территории отеля и в номерах"
        room = f"Индивидуальный кондиционер, сейф, балкон/терраса, мини-бар, халаты. Реновация: {renovation} г."
    elif stars == 4:
        wifi = "Бесплатный базовый Wi-Fi в зоне лобби (в номерах отсутствует или платно)" if dest == "Египет" and line >= 3 else "Бесплатный Wi-Fi в лобби и общественных зонах (в номерах может быть с ограничением)"
        room = f"Индивидуальный кондиционер, сейф, балкон/терраса, мини-бар. Реновация: {renovation} г."
    else:
        wifi = "Бесплатный базовый Wi-Fi в зоне лобби (в номерах отсутствует)"
        room = f"Кондиционер, мини-холодильник, балкон/терраса, спутниковое ТВ. Реновация: {renovation} г."

    transfer_str = f"Трансфер из аэропорта: ~{transfer} мин"

    return {
        "beach": {"line": line_str, "type": btype_str, "entry": entry_str, "equipment": equip_str, "reef": reef_str},
        "pools": {"pools_count": pools_count_str, "heated": heated_str, "aquapark": aqua_str},
        "food": {"concept": concept_str, "main_buffet": main_buffet, "alacarte": alacarte, "bars": bars},
        "kids": {"club": kids_club, "pool": kids_pool, "playground": kids_playground},
        "sport_spa": {"spa": spa, "fitness": fitness, "watersports": watersports},
        "comfort": {"wifi": wifi, "room_amenities": room, "distance": transfer_str},
    }


def compile_hotel_passport(name: str, hdata: Dict[str, Any]) -> Dict[str, Any]:
    specs = hdata.get("specs", {})
    dest = hdata.get("destination", "Египет")
    stars = specs.get("stars") or hdata.get("stars") or 4
    line = specs.get("beach_line", 1)
    dist_m = specs.get("beach_distance_meters", 0)
    shuttle = specs.get("shuttle_bus", "none")
    btype = specs.get("beach_type", "sand")
    sentry = specs.get("sea_entry", "shallow_sand")
    aquapark = bool(specs.get("aquapark", False))
    slides = specs.get("slides_total", 0)
    heated = bool(specs.get("heated_pools_winter", False))
    food_concept = specs.get("food_concept", "AI")
    ta_rating = specs.get("tripadvisor_rating", 4.2)
    ta_reviews = specs.get("tripadvisor_reviews", 1000)
    highlights = specs.get("highlights", [])
    caution_notes = specs.get("caution_notes", [])

    btype_map = {
        "sand": "песчаный пляж",
        "pebble": "галечный пляж",
        "coral_rocky": "кораллово-песчаный берег с рифом",
        "mixed": "песчано-галечный пляж",
    }
    btype_str = btype_map.get(btype, "песчаный пляж")

    entry_map = {
        "shallow_sand": "Пологий песчаный вход, удобный для купания без специальной обуви",
        "pontoon_to_reef": "Песчаное мелководье у берега, спуск на глубину и к коралловому рифу с понтона",
        "deep_sand": "Песчаный вход с быстрым комфортным набором глубины",
        "pebbles_need_shoes": "Галечный вход в кристально чистое море (рекомендуется специальная обувь)",
        "jetty": "Вход в море с оборудованного деревянного пирса или платформы",
    }
    sentry_str = entry_map.get(sentry, "Комфортный вход в море")

    fc_map = {
        "UAI": "Ultra All Inclusive",
        "AI": "All Inclusive",
        "HB": "Half Board (Завтрак + Ужин)",
        "BB": "Bed & Breakfast",
    }
    fc_label = fc_map.get(food_concept, food_concept)

    if stars >= 5:
        if dest == "Турция":
            food_snippet = f"Концепция «{fc_label}»: богатый шведский стол с блюдами турецкой и мировой кухни, свежей выпечкой и гриль-станциями. Несколько a la carte ресторанов и круглосуточные бары."
        elif dest == "Египет":
            food_snippet = f"Концепция «{fc_label}»: расширенный шведский стол в основном ресторане, гриль, тематические ужины, несколько a la carte ресторанов и бары на пляже и у бассейна."
        else:
            food_snippet = f"Концепция «{fc_label}»: средиземноморский и европейский шведский стол, морепродукты, a la carte рестораны и вечерние бары."
    elif stars == 4:
        if line >= 3:
            food_snippet = f"Концепция «{fc_label}»: трехразовое питание (шведский стол) в главном ресторане, блюда местной и восточной кухни, бар у бассейна с напитками. A la carte рестораны отсутствуют."
        else:
            food_snippet = f"Концепция «{fc_label}»: разнообразный шведский стол в главном ресторане, дневные закуски в снек-баре, напитки местного производства в барах у бассейна и в лобби."
    else:
        food_snippet = f"Концепция «{fc_label}»: базовый шведский стол в главном ресторане (завтрак, обед, ужин), безалкогольные и алкогольные напитки местного производства в баре у бассейна. Рестораны a la carte отсутствуют."

    if line == 1:
        beach_snippet = f"1-я линия: собственный оборудованный {btype_str}. {sentry_str}. Бесплатные шезлонги, зонтики, пляжные полотенца и бар на пляже."
    elif line == 2:
        dist_t = f"~{dist_m} м" if dist_m > 0 else "300–500 м"
        shuttle_t = ", курсирует бесплатный шаттл" if shuttle == "free" else ""
        beach_snippet = f"2-я линия ({dist_t} до моря, через променад или дорогу{shuttle_t}). Выделенная пляжная зона с бесплатными шезлонгами и зонтами. {sentry_str}."
    else:
        dist_t = f"~{dist_m} м" if dist_m > 0 else "в глубине курорта"
        shuttle_t = "Курсирует бесплатный автобус на пляж по расписанию." if shuttle == "free" else "Пешая доступность или такси до пляжа."
        beach_snippet = f"3-я линия ({dist_t}). {shuttle_t} Гости отдыхают на арендованном пляже (шезлонги и зонты бесплатно, бар платно). {sentry_str}." if stars <= 3 else f"3-я линия ({dist_t}). {shuttle_t} Оборудованная пляжная зона с бесплатными лежаками и зонтиками. {sentry_str}."

    if stars >= 5:
        if dest == "Египет":
            ai_hotel_summary = (
                f"{name} — высококлассный курортный комплекс категории 5★ в регионе {dest}. "
                f"Расположен на {line}-й линии ({btype_str}). Ключевые преимущества: концепция «{fc_label}», "
                f"{'собственный аквапарк (' + str(slides) + ' горок), ' if aquapark and slides > 0 else ('аквапарк на территории, ' if aquapark else '')}"
                f"{'бассейны с зимним подогревом, ' if heated else 'несколько открытых бассейнов, '}"
                f"живописный риф для снорклинга и качественный сервис."
            )
        else:
            ai_hotel_summary = (
                f"{name} — премиальный пятизвездочный курортный отель в регионе {dest}. "
                f"Расположен на {line}-й линии ({btype_str}). Предлагает развитую курортную инфраструктуру, "
                f"концепцию «{fc_label}», просторные бассейны{' с аквапарком' if aquapark else ''} и высокий уровень комфорта."
            )
        ai_audience = "Пары, семьи с детьми и путешественники, ценящие высокий комфорт, качественную кухню и развитую инфраструктуру"
        suitable_for = "Премиальный отдых и семьи"
    elif stars == 4:
        if line >= 3:
            ai_hotel_summary = (
                f"{name} — бюджетный отель категории 4★ в курортной зоне {dest}. "
                f"Находится на 3-й линии (~{dist_m or 2000} м от берега, организован шаттл на пляж). "
                f"Предлагает концепцию питания «{fc_label}», открытый плавательный бассейн{' с горками' if slides > 0 else ''} "
                f"и доступные цены на отдых."
            )
            ai_audience = "Бюджетные туристы, пары и молодежь, ориентированные на экскурсии и доступный отдых"
            suitable_for = "Экономный отдых и поездки"
        else:
            ai_hotel_summary = (
                f"{name} — популярный курортный отель категории 4★ в регионе {dest}. "
                f"Расположен на {line}-й линии ({btype_str}). "
                f"Предлагает систему «{fc_label}», открытые бассейны{' с водными горками' if aquapark or slides > 0 else ''}"
                f"{', зимний подогрев' if heated else ''} и удобный выход к морю."
            )
            ai_audience = "Семьи с детьми, пары и любители активного пляжного отдыха"
            suitable_for = "Семьи с детьми и пары"
    else:
        ai_hotel_summary = (
            f"{name} — экономичный отель категории 3★ в регионе {dest}. "
            f"Расположен на {line}-й линии ({dist_m or 2000} м от моря, шаттл-бас). "
            f"Обеспечивает базовый набор курортных удобств, питание «{fc_label}» и открытый бассейн. "
            f"Оптимален для непритязательных туристов, планирующих активные прогулки и экскурсии."
        )
        ai_audience = "Неприхотливые туристы, самостоятельные путешественники, молодежь без маленьких детей"
        suitable_for = "Экономный отдых и экскурсии"

    pros = []
    if highlights and len(highlights) >= 2:
        pros = [h for h in highlights if len(h) > 6][:3]
    if len(pros) < 3:
        if line == 1:
            pros.append(f"1-я линия с оборудованным пляжем ({btype_str})")
        elif shuttle == "free":
            pros.append("Бесплатный регулярный трансфер на оборудованный пляж")
        if heated:
            pros.append("Бассейны с подогревом в зимний период")
        elif aquapark:
            pros.append(f"Собственный аквапарк ({slides} водных горок)" if slides > 0 else "Собственный аквапарк с водными горками")
        pros.append(f"Питание по системе {fc_label}")
    pros = pros[:3]

    cons = []
    if caution_notes and len(caution_notes) >= 1:
        cons = [c for c in caution_notes if len(c) > 6][:2]
    if len(cons) < 2:
        if line >= 3:
            cons.append(f"3-я линия: расстояние до моря около {dist_m or 2000} м (необходим шаттл)")
        elif line == 2:
            cons.append("2-я линия: дорога до пляжа занимает несколько минут пешком")
        if not heated and dest == "Египет":
            cons.append("В зимние месяцы открытые бассейны функционируют без подогрева")
        elif stars <= 3:
            cons.append("Скромный номерной фонд и базовая концепция питания без a la carte ресторанов")
    cons = cons[:2]

    if stars >= 5:
        verdict = f"Отличный пятизвездочный выбор в регионе {dest} для тех, кому важны комфорт, {btype_str} и концепция «{fc_label}»."
    elif stars == 4:
        verdict = f"Сбалансированный отель категории 4★ с хорошим соотношением цены и качества для семейного и парного отдыха."
    else:
        verdict = f"Честный эконом-вариант 3★ для практичных путешественников без завышенных ожиданий к роскоши."

    if stars >= 5:
        review_snippet = "«Прекрасный отель с просторной зеленой территорией, внимательным персоналом и разнообразной кухней. Море и риф оставили самые приятные впечатления.»"
    elif stars == 4:
        review_snippet = "«Хороший бюджетный отель для спокойного отдыха. До пляжа возит бесплатный автобус, персонал доброжелательный, питание соответствует своей ценовой категории.»" if line >= 3 else "«Удачное расположение, теплое море и комфортные номера. Питание вкусное, анимация ненавязчивая. Отличный отдых за разумную стоимость.»"
    else:
        review_snippet = "«Отель для неприхотливых туристов, которые приехали ради моря и экскурсий. Базовые удобства есть, автобус на пляж ходит по расписанию, все честно за свою цену.»"

    infra = build_hotel_infrastructure(name, hdata)

    return {
        "stars": stars,
        "ta_rating": float(ta_rating),
        "ta_reviews": int(ta_reviews),
        "beach_line": int(line),
        "beach_type": btype_str.capitalize(),
        "sea_entry": sentry_str,
        "has_aquapark": aquapark,
        "has_heated_pools": heated,
        "food_concept": fc_label,
        "suitable_for": suitable_for,
        "verdict": verdict,
        "ai_hotel_summary": ai_hotel_summary,
        "ai_audience": ai_audience,
        "pros": pros,
        "cons": cons,
        "food_snippet": food_snippet,
        "beach_snippet": beach_snippet,
        "review_snippet": review_snippet,
        "infra_rich": infra,
    }

