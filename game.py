# -*- coding: utf-8 -*-
"""Логика игры «Строй Империю».

Модуль не зависит от Kivy, поэтому его можно запускать и тестировать
отдельно (см. tests/test_game.py).
"""

import json
import math
import os
import random

PLAYER = "p"
MAX_LEVEL = 8
TRUCE_TURNS = 5
MAX_CITIES = 10
AI_INCOME_MULT = (0.75, 0.9, 1.15)  # легко / нормально / сложно
DIFFICULTY_NAMES = ("Легко", "Нормально", "Сложно")

RESOURCES = ("gold", "food", "wood", "stone")
RES_NAMES = {"gold": "Золото", "food": "Еда", "wood": "Дерево", "stone": "Камень"}
RES_SHORT = {"gold": "зол", "food": "еда", "wood": "дер", "stone": "кам"}

BUILDINGS = {
    "farm": {
        "name": "Ферма", "desc": "+10 еды за ход",
        "base": {"wood": 40, "stone": 10}, "prod": ("food", 10),
    },
    "sawmill": {
        "name": "Лесопилка", "desc": "+8 дерева за ход",
        "base": {"gold": 40, "stone": 10}, "prod": ("wood", 8),
    },
    "quarry": {
        "name": "Каменоломня", "desc": "+6 камня за ход",
        "base": {"gold": 40, "wood": 30}, "prod": ("stone", 6),
    },
    "market": {
        "name": "Рынок", "desc": "+12 золота за ход",
        "base": {"wood": 50, "stone": 30}, "prod": ("gold", 12),
    },
    "barracks": {
        "name": "Казарма", "desc": "Найм войск, +5% к силе армии",
        "base": {"gold": 80, "wood": 40, "stone": 40}, "prod": None,
    },
    "walls": {
        "name": "Стены", "desc": "+15% к обороне города",
        "base": {"stone": 80, "wood": 20}, "prod": None,
    },
}
BUILD_ORDER = ["farm", "sawmill", "quarry", "market", "barracks", "walls"]

UNITS = {
    "spear": {
        "name": "Копейщики", "cost": {"gold": 20, "food": 10},
        "atk": 4, "def": 6, "upkeep": 0.5, "beats": "cav",
        "note": "сильны против кавалерии",
    },
    "archer": {
        "name": "Лучники", "cost": {"gold": 30, "wood": 15},
        "atk": 7, "def": 3, "upkeep": 0.5, "beats": "spear",
        "note": "сильны против копейщиков",
    },
    "cav": {
        "name": "Кавалерия", "cost": {"gold": 55, "food": 25},
        "atk": 10, "def": 4, "upkeep": 1.0, "beats": "archer",
        "note": "сильна против лучников",
    },
    "siege": {
        "name": "Катапульты", "cost": {"gold": 70, "wood": 40, "stone": 30},
        "atk": 14, "def": 1, "upkeep": 1.0, "beats": None,
        "note": "ослабляют стены врага",
    },
}
UNIT_ORDER = ["spear", "archer", "cav", "siege"]

# id, название, цвет, агрессивность, города
COUNTRY_DEFS = [
    ("c1", "Королевство Альдрия", [0.88, 0.27, 0.27], 0.55, ["Альдор", "Ривенхолл"]),
    ("c2", "Империя Каргот", [0.25, 0.72, 0.35], 0.80, ["Каргот", "Серый Брод"]),
    ("c3", "Республика Вельмор", [0.95, 0.80, 0.22], 0.25, ["Вельмор", "Тихая Гавань"]),
    ("c4", "Ханство Зарак", [0.66, 0.36, 0.86], 0.70, ["Зарак-Тал", "Песчаный Оплот"]),
    ("c5", "Орден Севера", [0.95, 0.56, 0.18], 0.45, ["Нордхейм", "Ледяной Шпиль"]),
]
PLAYER_COLOR = [0.25, 0.55, 0.98]
PLAYER_CITY_NAMES = ["Столица", "Приморск"]
NEUTRAL_NAMES = [
    "Зелёная Долина", "Старый Мост", "Каменный Перевал", "Лунный Порт",
    "Янтарные Холмы", "Дубрава", "Соляные Копи", "Речной Узел",
]


# ----------------------------------------------------------------- утилиты
def empty_army():
    return {u: 0 for u in UNIT_ORDER}


def fmt_cost(cost):
    return ", ".join("%s %d" % (RES_SHORT[r], cost[r])
                     for r in RESOURCES if cost.get(r, 0) > 0)


def fmt_army(army):
    parts = ["%s %d" % (UNITS[u]["name"], army[u])
             for u in UNIT_ORDER if army.get(u, 0) > 0]
    return ", ".join(parts) if parts else "нет"


def army_power(army, enemy_army, side):
    """Сила армии (side = 'atk' или 'def') с учётом «камень-ножницы-бумага»."""
    total_enemy = sum(enemy_army.values())
    power = 0.0
    for u, n in army.items():
        if n <= 0:
            continue
        mult = 1.0
        beats = UNITS[u]["beats"]
        if beats and total_enemy > 0:
            mult += 0.5 * enemy_army.get(beats, 0) / float(total_enemy)
        power += n * UNITS[u][side] * mult
    return power


def hex_color(c):
    return "%02x%02x%02x" % tuple(int(max(0.0, min(1.0, v)) * 255) for v in c[:3])


# -------------------------------------------------------------------- игра
class Game(object):
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.turn = 1
        self.difficulty = 1
        self.countries = {}
        self.cities = {}
        self.rel = {}
        self.log = []
        self.offers = []
        self.over = None  # None / "win" / "lose"

    # ------------------------------------------------------ создание мира
    def _new_country(self, cid, name, color, is_player, aggr, army, res):
        return {
            "id": cid, "name": name, "color": list(color), "player": is_player,
            "res": res, "army": army, "returning": empty_army(),
            "alive": True, "aggr": aggr, "capital": None, "asked": -1,
        }

    def new_game(self, player_name="Моя империя", difficulty=1):
        self.turn = 1
        self.difficulty = max(0, min(2, int(difficulty)))
        self.countries = {}
        self.cities = {}
        self.rel = {}
        self.log = []
        self.offers = []
        self.over = None
        rng = self.rng

        a = empty_army()
        a.update({"spear": 8, "archer": 4})
        self.countries[PLAYER] = self._new_country(
            PLAYER, (player_name or "Моя империя").strip()[:28], PLAYER_COLOR, True, 0.0, a,
            {"gold": 250, "food": 150, "wood": 150, "stone": 100})
        start_mult = (0.8, 0.95, 1.15)[self.difficulty]
        for cid, name, color, aggr, _ in COUNTRY_DEFS:
            a = empty_army()
            a.update({"spear": 8, "archer": 4, "cav": 2})
            res = {"gold": int(250 * start_mult), "food": int(150 * start_mult),
                   "wood": int(150 * start_mult), "stone": int(100 * start_mult)}
            self.countries[cid] = self._new_country(cid, name, color, False, aggr, a, res)

        # расположение на карте: 6 областей по кругу, игрок внизу
        slot_of = {PLAYER: 4}
        rest = [0, 1, 2, 3, 5]
        for i, d in enumerate(COUNTRY_DEFS):
            slot_of[d[0]] = rest[i]
        placed = []

        def place(cx, cy, spread):
            x, y = cx, cy
            for _ in range(300):
                x = min(0.92, max(0.08, cx + rng.uniform(-spread, spread)))
                y = min(0.92, max(0.08, cy + rng.uniform(-spread, spread)))
                if all((x - px) ** 2 + (y - py) ** 2 >= 0.085 ** 2 for px, py in placed):
                    break
            placed.append((x, y))
            return x, y

        tid = 0
        defs = [(PLAYER, PLAYER_CITY_NAMES)] + [(d[0], d[4]) for d in COUNTRY_DEFS]
        for cid, names in defs:
            ang = math.radians(60 * slot_of[cid] + 15)
            cx, cy = 0.5 + 0.30 * math.cos(ang), 0.5 + 0.30 * math.sin(ang)
            for k, nm in enumerate(names):
                x, y = place(cx, cy, 0.10)
                b = ({"farm": 1, "sawmill": 1, "quarry": 1, "market": 1, "barracks": 1}
                     if k == 0 else {"farm": 1, "sawmill": 1})
                city_id = "t%d" % tid
                tid += 1
                self.cities[city_id] = {"id": city_id, "name": nm, "owner": cid,
                                        "b": b, "x": x, "y": y}
                if k == 0:
                    self.countries[cid]["capital"] = city_id
        for nm in NEUTRAL_NAMES:
            x, y = place(rng.uniform(0.2, 0.8), rng.uniform(0.2, 0.8), 0.25)
            city_id = "t%d" % tid
            tid += 1
            self.cities[city_id] = {"id": city_id, "name": nm, "owner": None,
                                    "b": {}, "x": x, "y": y}

        ids = list(self.countries.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                self.rel[self._rkey(ids[i], ids[j])] = {"war": False, "truce": 0, "since": 0}
        self.log.append("Игра началась. Развивайте города, стройте казармы и армию. "
                        "Свободные земли на карте можно занять и основать новые города.")

    # --------------------------------------------------------- справочные
    @staticmethod
    def _rkey(a, b):
        return "|".join(sorted([a, b]))

    def get_rel(self, a, b):
        return self.rel[self._rkey(a, b)]

    def at_war(self, a, b):
        return a != b and self.get_rel(a, b)["war"]

    def enemies(self, cid):
        return [o for o, c in self.countries.items()
                if o != cid and c["alive"] and self.at_war(cid, o)]

    def alive_ids(self):
        return [cid for cid, c in self.countries.items() if c["alive"]]

    def cities_of(self, cid):
        return [c for c in self.cities.values() if c["owner"] == cid]

    def free_sites(self):
        return [c for c in self.cities.values() if c["owner"] is None]

    def building_total(self, cid, bid):
        return sum(c["b"].get(bid, 0) for c in self.cities_of(cid))

    def army_bonus(self, cid):
        return 1.0 + 0.05 * min(10, self.building_total(cid, "barracks"))

    def army_size(self, cid):
        c = self.countries[cid]
        return sum(c["army"].values()) + sum(c["returning"].values())

    def army_cap(self, cid):
        return 30 + 15 * self.building_total(cid, "barracks")

    def power(self, cid):
        c = self.countries[cid]
        total = 0
        for src in (c["army"], c["returning"]):
            for u, n in src.items():
                total += n * (UNITS[u]["atk"] + UNITS[u]["def"])
        return int(total * self.army_bonus(cid))

    def production(self, cid):
        c = self.countries[cid]
        prod = {r: 0 for r in RESOURCES}
        for city in self.cities_of(cid):
            prod["gold"] += 5
            for bid, lvl in city["b"].items():
                p = BUILDINGS[bid]["prod"]
                if p:
                    prod[p[0]] += p[1] * lvl
        prod["gold"] += 10
        if not c["player"]:
            m = AI_INCOME_MULT[self.difficulty]
            prod = {r: int(v * m) for r, v in prod.items()}
        return prod

    def upkeep(self, cid):
        c = self.countries[cid]
        total = 0.0
        for src in (c["army"], c["returning"]):
            for u, n in src.items():
                total += UNITS[u]["upkeep"] * n
        return int(math.ceil(total))

    def net_income(self, cid):
        p = self.production(cid)
        p["food"] -= self.upkeep(cid)
        return p

    # ------------------------------------------------------- ресурсы/стройка
    def can_afford(self, cid, cost):
        res = self.countries[cid]["res"]
        return all(res[r] >= v for r, v in cost.items())

    def pay(self, cid, cost):
        res = self.countries[cid]["res"]
        for r, v in cost.items():
            res[r] -= v

    def build_cost(self, city_id, bid):
        lvl = self.cities[city_id]["b"].get(bid, 0)
        return {r: int(round(v * (1.55 ** lvl))) for r, v in BUILDINGS[bid]["base"].items()}

    def build(self, cid, city_id, bid):
        city = self.cities.get(city_id)
        if not city or city["owner"] != cid:
            return False, "Это не ваш город."
        lvl = city["b"].get(bid, 0)
        if lvl >= MAX_LEVEL:
            return False, "Достигнут максимальный уровень."
        cost = self.build_cost(city_id, bid)
        if not self.can_afford(cid, cost):
            return False, "Не хватает ресурсов: " + fmt_cost(cost)
        self.pay(cid, cost)
        city["b"][bid] = lvl + 1
        return True, "%s, город %s: уровень %d." % (BUILDINGS[bid]["name"], city["name"], lvl + 1)

    def found_cost(self, cid):
        n = len(self.cities_of(cid))
        return {"gold": 150 + 75 * n, "wood": 80 + 30 * n, "stone": 60 + 30 * n}

    def found_city(self, cid, city_id):
        city = self.cities.get(city_id)
        if not city or city["owner"] is not None:
            return False, "Эта земля уже занята."
        if len(self.cities_of(cid)) >= MAX_CITIES:
            return False, "Достигнут предел числа городов (%d)." % MAX_CITIES
        cost = self.found_cost(cid)
        if not self.can_afford(cid, cost):
            return False, "Не хватает ресурсов: " + fmt_cost(cost)
        self.pay(cid, cost)
        city["owner"] = cid
        city["b"] = {"farm": 1}
        return True, "Основан город «%s»." % city["name"]

    def recruit(self, cid, unit, n):
        if self.building_total(cid, "barracks") <= 0:
            return False, "Постройте Казарму, чтобы нанимать войска."
        room = self.army_cap(cid) - self.army_size(cid)
        if room <= 0:
            return False, "Достигнут лимит армии (%d). Стройте казармы." % self.army_cap(cid)
        n = min(n, room)
        cost = {r: v * n for r, v in UNITS[unit]["cost"].items()}
        if not self.can_afford(cid, cost):
            return False, "Не хватает ресурсов: " + fmt_cost(cost)
        self.pay(cid, cost)
        self.countries[cid]["army"][unit] += n
        return True, "Нанято: %s x%d." % (UNITS[unit]["name"], n)

    # ------------------------------------------------------------ дипломатия
    def declare_war(self, a, b):
        if a == b or not self.countries[b]["alive"]:
            return False, "Нельзя объявить войну этой стране."
        r = self.get_rel(a, b)
        if r["war"]:
            return False, "Вы уже воюете."
        if r["truce"] > 0:
            return False, "Действует перемирие: ещё %d ход." % r["truce"]
        r["war"] = True
        r["since"] = self.turn
        return True, "Война объявлена: «%s»." % self.countries[b]["name"]

    def make_peace(self, a, b):
        r = self.get_rel(a, b)
        r["war"] = False
        r["truce"] = TRUCE_TURNS
        self.offers = [x for x in self.offers if x not in (a, b)]

    def propose_peace(self, b):
        """Игрок предлагает мир стране b."""
        if not self.at_war(PLAYER, b):
            return False, "Вы не воюете с этой страной."
        r = self.get_rel(PLAYER, b)
        c = self.countries[b]
        if self.turn - r["since"] < 2:
            return False, "Слишком рано просить мира."
        if c["asked"] == self.turn:
            return False, "Вы уже предлагали мир в этом ходу."
        c["asked"] = self.turn
        ratio = (self.power(b) + 10.0) / (self.power(PLAYER) + 10.0)
        p = 0.75 - 0.45 * c["aggr"] + 0.25 * (1.0 - min(2.0, ratio))
        p = max(0.05, min(0.95, p))
        if self.rng.random() < p:
            self.make_peace(PLAYER, b)
            return True, "«%s» принимает мир. Перемирие на %d ходов." % (c["name"], TRUCE_TURNS)
        return False, "«%s» отвергает предложение мира." % c["name"]

    def accept_offer(self, b):
        if b not in self.offers:
            return False, "Предложение больше не действует."
        self.make_peace(PLAYER, b)
        return True, "Мир заключён. Перемирие на %d ходов." % TRUCE_TURNS

    # ------------------------------------------------------------------ бой
    @staticmethod
    def _sent(country, pct):
        sent = {}
        for u in UNIT_ORDER:
            n = int(country["army"][u] * pct / 100.0)
            if n > 0:
                sent[u] = n
        return sent

    def _defense_power(self, did, city, sent):
        d = self.countries[did]
        base = army_power(d["army"], sent, "def") * self.army_bonus(did)
        base += 20 + 4 * sum(city["b"].values())  # городское ополчение
        walls = city["b"].get("walls", 0)
        siege = sent.get("siege", 0)
        mult = 1.0 + 0.15 * walls * (1.0 - min(0.75, 0.05 * siege))
        return base * mult

    def battle_preview(self, aid, city_id, pct):
        """Оценка (сила атаки, сила обороны, число отправляемых воинов)."""
        city = self.cities[city_id]
        did = city["owner"]
        sent = self._sent(self.countries[aid], pct)
        if did is None or not sent:
            return 0, 0, 0
        a_pow = army_power(sent, self.countries[did]["army"], "atk") * self.army_bonus(aid)
        d_pow = self._defense_power(did, city, sent)
        return int(a_pow), int(d_pow), sum(sent.values())

    def attack(self, aid, city_id, pct):
        """Атака страны aid на город city_id. Возвращает (ok, текст, отчёт)."""
        a = self.countries[aid]
        city = self.cities.get(city_id)
        if not city or city["owner"] is None:
            return False, "Нейтральные земли атаковать нельзя.", None
        did = city["owner"]
        if did == aid:
            return False, "Это ваш город.", None
        if not self.at_war(aid, did):
            return False, "Вы не воюете с этой страной.", None
        sent = self._sent(a, pct)
        if not sent:
            return False, "Нет войск для атаки.", None
        d = self.countries[did]
        for u, n in sent.items():
            a["army"][u] -= n

        rng = self.rng
        a_pow = army_power(sent, d["army"], "atk") * self.army_bonus(aid) * rng.uniform(0.9, 1.1)
        d_pow = self._defense_power(did, city, sent) * rng.uniform(0.9, 1.1)
        win = a_pow > d_pow
        if win:
            r = d_pow / a_pow
            a_loss = 0.12 + 0.40 * r
            d_loss = 0.50 + 0.30 * (1.0 - r)
        else:
            r = a_pow / d_pow
            a_loss = 0.50 + 0.30 * (1.0 - r)
            d_loss = 0.12 + 0.40 * r

        a_lost, d_lost = empty_army(), empty_army()
        for u, n in sent.items():
            a_lost[u] = min(n, int(round(n * a_loss)))
            a["returning"][u] += n - a_lost[u]
        for u in UNIT_ORDER:
            n = d["army"][u]
            d_lost[u] = min(n, int(round(n * d_loss)))
            d["army"][u] -= d_lost[u]

        loot = {r_: 0 for r_ in RESOURCES}
        if win:
            city["owner"] = aid
            for bid in list(city["b"].keys()):
                if city["b"][bid] > 1:
                    city["b"][bid] -= 1
            for r_ in RESOURCES:
                loot[r_] = int(d["res"][r_] * 0.25)
                d["res"][r_] -= loot[r_]
                a["res"][r_] += loot[r_]
            if d["capital"] == city_id:
                left = self.cities_of(did)
                d["capital"] = left[0]["id"] if left else None

        rep = {"att_id": aid, "def_id": did, "city": city["name"], "win": win,
               "a_pow": int(a_pow), "d_pow": int(d_pow),
               "a_lost": a_lost, "d_lost": d_lost, "loot": loot, "extra": []}
        rep["extra"] = self._check_state()
        text = self.battle_text(rep, aid)
        if aid == PLAYER:
            self.log.append("[Ход %d] %s" % (self.turn, text.split("\n")[0]))
        return True, text, rep

    def battle_text(self, rep, viewer):
        att = self.countries[rep["att_id"]]
        dfn = self.countries[rep["def_id"]]
        lines = []
        if viewer == rep["att_id"]:
            if rep["win"]:
                lines.append("ПОБЕДА! Город «%s» захвачен." % rep["city"])
            else:
                lines.append("ПОРАЖЕНИЕ. Атака на «%s» отбита." % rep["city"])
            lines.append("Сила атаки %d против обороны %d." % (rep["a_pow"], rep["d_pow"]))
            lines.append("Ваши потери: " + fmt_army(rep["a_lost"]) + ".")
            lines.append("Потери врага: " + fmt_army(rep["d_lost"]) + ".")
            if rep["win"] and any(rep["loot"].values()):
                lines.append("Добыча: " + fmt_cost(rep["loot"]) + ".")
            lines.append("Уцелевшие войска вернутся домой на следующем ходу.")
        else:
            lines.append("«%s» напала на город «%s»: %s" % (
                att["name"], rep["city"],
                "ГОРОД ПОТЕРЯН!" if rep["win"] else "атака отбита."))
            lines.append("Сила атаки %d, ваша оборона %d." % (rep["a_pow"], rep["d_pow"]))
            lines.append("Ваши потери: " + fmt_army(rep["d_lost"]) + ".")
            lines.append("Потери врага: " + fmt_army(rep["a_lost"]) + ".")
        if rep["extra"]:
            lines.extend(rep["extra"])
        return "\n".join(lines)

    def _check_state(self):
        msgs = []
        for cid, c in self.countries.items():
            if c["alive"] and not self.cities_of(cid):
                c["alive"] = False
                c["army"] = empty_army()
                c["returning"] = empty_army()
                self.offers = [x for x in self.offers if x != cid]
                for o in self.countries:
                    if o != cid:
                        self.get_rel(cid, o)["war"] = False
                msgs.append("Страна «%s» пала: у неё не осталось городов." % c["name"])
        if self.over is None:
            if not self.countries[PLAYER]["alive"]:
                self.over = "lose"
                msgs.append("Вы потеряли все города. Игра окончена.")
            elif not any(c["alive"] for cid, c in self.countries.items() if cid != PLAYER):
                self.over = "win"
                msgs.append("Все соперники повержены. ВЫ ПОБЕДИЛИ!")
        return msgs

    # ----------------------------------------------------------- конец хода
    def _random_event(self):
        res = self.countries[PLAYER]["res"]
        k = self.rng.choice(["harvest", "caravan", "raid", "fire", "ore"])
        if k == "harvest":
            v = self.rng.randint(60, 140)
            res["food"] += v
            return "Богатый урожай: +%d еды." % v
        if k == "caravan":
            v = self.rng.randint(80, 160)
            res["gold"] += v
            return "Торговый караван заплатил пошлину: +%d золота." % v
        if k == "raid":
            v = int(res["gold"] * self.rng.uniform(0.08, 0.18))
            res["gold"] -= v
            return "Разбойники ограбили казну: -%d золота." % v
        if k == "fire":
            v = int(res["wood"] * 0.2)
            res["wood"] -= v
            return "Пожар на складах: -%d дерева." % v
        v = self.rng.randint(40, 90)
        res["stone"] += v
        return "Найдена жила камня: +%d камня." % v

    def end_turn(self):
        if self.over:
            return []
        msgs = []
        self.offers = []

        for cid, c in self.countries.items():
            if not c["alive"]:
                continue
            for u in UNIT_ORDER:
                c["army"][u] += c["returning"][u]
                c["returning"][u] = 0
            prod = self.production(cid)
            up = self.upkeep(cid)
            for r in RESOURCES:
                c["res"][r] += prod[r]
            c["res"]["food"] -= up
            if cid == PLAYER:
                msgs.append("Доход за ход: золото %+d, еда %+d, дерево %+d, камень %+d." % (
                    prod["gold"], prod["food"] - up, prod["wood"], prod["stone"]))
            if c["res"]["food"] < 0:
                c["res"]["food"] = 0
                lost = 0
                for u in UNIT_ORDER:
                    n = c["army"][u]
                    l = int(math.ceil(n * 0.1)) if n else 0
                    c["army"][u] = n - l
                    lost += l
                if cid == PLAYER and lost:
                    msgs.append("ГОЛОД! Не хватает еды на армию: разбежалось %d воинов. "
                                "Стройте фермы." % lost)

        for r in self.rel.values():
            if r["truce"] > 0:
                r["truce"] -= 1

        if self.rng.random() < 0.18:
            msgs.append(self._random_event())

        ai = [cid for cid in self.alive_ids() if cid != PLAYER]
        self.rng.shuffle(ai)
        for cid in ai:
            if self.countries[cid]["alive"] and not self.over:
                self._ai_turn(cid, msgs)

        msgs.extend(self._check_state())
        for m in msgs:
            self.log.append("[Ход %d] %s" % (self.turn, m))
        self.log = self.log[-300:]
        self.turn += 1
        return msgs

    # ------------------------------------------------------------------- ИИ
    def _ai_turn(self, cid, msgs):
        self._ai_build(cid)
        self._ai_recruit(cid)
        self._ai_expand(cid)
        self._ai_diplomacy(cid, msgs)
        if self.countries[cid]["alive"]:
            self._ai_attack(cid, msgs)

    def _ai_build(self, cid):
        rng = self.rng
        war = bool(self.enemies(cid))
        for _ in range(3):
            cs = self.cities_of(cid)
            if not cs:
                return
            city = rng.choice(cs)
            food_net = self.net_income(cid)["food"]
            keys = ["farm", "sawmill", "quarry", "market", "barracks", "walls"]
            weights = [4.0 if food_net < 8 else 1.0, 1.5, 1.5, 2.5,
                       2.0 if self.building_total(cid, "barracks") < 4 else 0.7,
                       2.5 if war else 0.8]
            bid = rng.choices(keys, weights=weights)[0]
            self.build(cid, city["id"], bid)

    def _ai_recruit(self, cid):
        rng = self.rng
        c = self.countries[cid]
        if self.building_total(cid, "barracks") <= 0:
            return
        war = bool(self.enemies(cid))
        budget = c["res"]["gold"] * (0.6 if war else 0.35)
        spent = 0
        for _ in range(20):
            if self.net_income(cid)["food"] < -3 and c["res"]["food"] < 120:
                break
            opts = ["spear", "archer", "cav"] + (["siege"] if war else [])
            wts = [3, 2, 2] + ([1] if war else [])
            u = rng.choices(opts, weights=wts)[0]
            if spent + UNITS[u]["cost"]["gold"] > budget:
                break
            ok, _ = self.recruit(cid, u, 1)
            if ok:
                spent += UNITS[u]["cost"]["gold"]

    def _ai_expand(self, cid):
        if len(self.cities_of(cid)) >= 6 or self.rng.random() > 0.2:
            return
        sites = self.free_sites()
        if not sites:
            return
        cost = self.found_cost(cid)
        if self.countries[cid]["res"]["gold"] < cost["gold"] + 100:
            return
        self.found_city(cid, self.rng.choice(sites)["id"])

    def _ai_diplomacy(self, cid, msgs):
        rng = self.rng
        c = self.countries[cid]
        for oid in list(self.enemies(cid)):
            dur = self.turn - self.get_rel(cid, oid)["since"]
            if oid == PLAYER:
                ratio = (self.power(cid) + 10.0) / (self.power(PLAYER) + 10.0)
                if dur >= 3 and ratio < 0.6 and cid not in self.offers and rng.random() < 0.35:
                    self.offers.append(cid)
                    msgs.append("«%s» просит мира. Вкладка «Дипломатия»." % c["name"])
            elif dur >= 6 and rng.random() < 0.12:
                self.make_peace(cid, oid)
                msgs.append("Мир между «%s» и «%s»." % (c["name"], self.countries[oid]["name"]))
        if self.turn < 6 or self.enemies(cid) or rng.random() > 0.05 + 0.12 * c["aggr"]:
            return
        mine = self.power(cid)
        cand, wts = [], []
        for oid in self.alive_ids():
            if oid == cid or self.get_rel(cid, oid)["truce"] > 0:
                continue
            w = ((mine + 10.0) / (self.power(oid) + 10.0)) ** 2
            if oid == PLAYER:
                w *= 1.3
            cand.append(oid)
            wts.append(max(0.05, w))
        if not cand:
            return
        oid = rng.choices(cand, weights=wts)[0]
        ok, _ = self.declare_war(cid, oid)
        if ok:
            if oid == PLAYER:
                msgs.append("«%s» объявила вам ВОЙНУ!" % c["name"])
            else:
                msgs.append("«%s» объявила войну «%s»." % (c["name"], self.countries[oid]["name"]))

    def _ai_attack(self, cid, msgs):
        c = self.countries[cid]
        enemies = self.enemies(cid)
        if not enemies or sum(c["army"].values()) == 0:
            return
        best, best_ratio = None, 0.0
        for eid in enemies:
            for city in self.cities_of(eid):
                a_pow, d_pow, _ = self.battle_preview(cid, city["id"], 85)
                if a_pow <= 0:
                    continue
                ratio = a_pow / float(max(1, d_pow))
                if ratio > best_ratio:
                    best, best_ratio = city, ratio
        if best is None:
            return
        reckless = c["aggr"] > 0.65 and best_ratio > 0.9 and self.rng.random() < 0.2
        if best_ratio < 1.15 and not reckless:
            return
        ok, _, rep = self.attack(cid, best["id"], 85)
        if not ok:
            return
        if rep["def_id"] == PLAYER:
            msgs.append(self.battle_text(rep, PLAYER))
        else:
            if rep["win"]:
                msgs.append("«%s» захватила город «%s» у «%s»." % (
                    c["name"], rep["city"], self.countries[rep["def_id"]]["name"]))
            msgs.extend(rep["extra"])

    # ------------------------------------------------------------- сохранение
    def to_dict(self):
        return {"v": 1, "turn": self.turn, "difficulty": self.difficulty,
                "countries": self.countries, "cities": self.cities, "rel": self.rel,
                "log": self.log[-300:], "offers": self.offers, "over": self.over}

    @classmethod
    def from_dict(cls, d):
        g = cls()
        g.turn = d["turn"]
        g.difficulty = d["difficulty"]
        g.countries = d["countries"]
        g.cities = d["cities"]
        g.rel = d["rel"]
        g.log = d["log"]
        g.offers = d["offers"]
        g.over = d["over"]
        return g

    def save(self, path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
