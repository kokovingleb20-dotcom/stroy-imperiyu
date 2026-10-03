# -*- coding: utf-8 -*-
"""Строй Империю — пошаговая стратегия для Android (Kivy).

Запуск на компьютере:  python main.py
Сборка APK: см. README.md
"""
import os

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform

from game import (BUILD_ORDER, BUILDINGS, DIFFICULTY_NAMES, MAX_CITIES, MAX_LEVEL, PLAYER,
                  RESOURCES, RES_NAMES, UNIT_ORDER, UNITS, Game, fmt_army, fmt_cost, hex_color)

BG = (0.07, 0.08, 0.11, 1)
CARD = (0.14, 0.16, 0.21, 1)
ACCENT = (0.20, 0.52, 0.86, 1)
GOOD = (0.17, 0.58, 0.33, 1)
DANGER = (0.74, 0.24, 0.24, 1)
MUTED = (0.24, 0.26, 0.31, 1)
TEXT = (0.92, 0.94, 0.97, 1)
SUB = (0.62, 0.67, 0.75, 1)

TABS = [("cities", "Города"), ("army", "Армия"), ("map", "Карта"),
        ("diplo", "Страны"), ("log", "Журнал")]

HELP_TEXT = (
    "ЦЕЛЬ: захватить все города соперников. Если вы потеряете все свои города, игра проиграна.\n\n"
    "ЭКОНОМИКА. Каждый ход города приносят золото, еду, дерево и камень. Улучшайте "
    "здания во вкладке «Города». Армия ест еду: без ферм начнётся голод и воины разбегутся.\n\n"
    "АРМИЯ. Для найма нужна Казарма. Копейщики бьют кавалерию, кавалерия бьёт лучников, "
    "лучники бьют копейщиков. Катапульты ослабляют стены. Размер армии ограничен казармами.\n\n"
    "ВОЙНА. Объявите войну (вкладка «Страны» или город врага на карте) и атакуйте город. "
    "Победа захватывает город и часть казны врага. Уцелевшие войска возвращаются домой "
    "только на следующем ходу, поэтому оставляйте часть армии для защиты.\n\n"
    "МИР. После мира 5 ходов действует перемирие. Соперники тоже воюют друг с другом "
    "и могут напасть на вас.\n\n"
    "РАСШИРЕНИЕ. Свободные земли на карте (серые) можно занять и основать там город."
)


# ------------------------------------------------------------ виджеты-помощники
class FLabel(Label):
    """Подпись, выровненная внутри своей области (слева по центру)."""

    def __init__(self, **kw):
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        kw.setdefault("color", TEXT)
        kw.setdefault("font_size", sp(13))
        super(FLabel, self).__init__(**kw)
        self.bind(size=self._upd)
        self._upd()

    def _upd(self, *args):
        self.text_size = (self.width, self.height)


class WLabel(Label):
    """Многострочная подпись, сама подбирающая высоту под текст."""

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "top")
        kw.setdefault("color", TEXT)
        kw.setdefault("font_size", sp(14))
        super(WLabel, self).__init__(**kw)
        self.bind(width=self._upd, texture_size=self._upd)
        self._upd()

    def _upd(self, *args):
        self.text_size = (self.width, None)
        self.height = max(dp(20), self.texture_size[1] + dp(4))


class Card(BoxLayout):
    def __init__(self, bg=CARD, **kw):
        kw.setdefault("orientation", "vertical")
        kw.setdefault("size_hint_y", None)
        kw.setdefault("padding", dp(10))
        kw.setdefault("spacing", dp(6))
        super(Card, self).__init__(**kw)
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*bg)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size


def darker(c, k=0.7):
    return (c[0] * k, c[1] * k, c[2] * k, 1)


def make_btn(text, on_press=None, color=ACCENT, height=48, width=None, font=15, disabled=False):
    b = Button(text=text, size_hint_y=None, height=dp(height), background_normal="",
               background_down="", background_disabled_normal="",
               background_color=MUTED if disabled else color, color=TEXT,
               disabled_color=(0.62, 0.64, 0.70, 1), font_size=sp(font),
               halign="center", valign="middle")
    if width is not None:
        b.size_hint_x = None
        b.width = dp(width)
    b.bind(size=lambda inst, v: setattr(inst, "text_size", (v[0] - dp(8), v[1])))
    b.disabled = disabled
    if not disabled:
        b.bind(state=lambda inst, st: setattr(inst, "background_color",
                                              darker(color) if st == "down" else color))
        if on_press is not None:
            b.bind(on_release=lambda *_: on_press())
    return b


def row(height, **kw):
    kw.setdefault("spacing", dp(6))
    return BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(height), **kw)


# -------------------------------------------------------------- главный экран
class Root(BoxLayout):
    def __init__(self, **kw):
        super(Root, self).__init__(orientation="vertical", spacing=dp(4),
                                   padding=[dp(6), dp(6), dp(6), dp(6)], **kw)
        self.game = None
        self.tab = "cities"
        self.popups = []
        self.scroll_pos = {}
        self.sv = None

        head = Card(size_hint_y=None, padding=dp(6), spacing=dp(4))
        top = row(46)
        titles = BoxLayout(orientation="vertical")
        self.name_lbl = FLabel(text="", bold=True, font_size=sp(16), shorten=True)
        self.info_lbl = FLabel(text="", font_size=sp(12), color=SUB)
        titles.add_widget(self.name_lbl)
        titles.add_widget(self.info_lbl)
        top.add_widget(titles)
        top.add_widget(make_btn("Меню", self.open_menu, color=MUTED, height=46, width=64, font=14))
        top.add_widget(make_btn("Конец\nхода", self.end_turn, color=GOOD, height=46, width=86, font=14))
        head.add_widget(top)
        resbar = row(40, spacing=dp(2))
        self.res_lbls = {}
        for r in RESOURCES:
            lbl = FLabel(text="", halign="center", markup=True, font_size=sp(12))
            self.res_lbls[r] = lbl
            resbar.add_widget(lbl)
        head.add_widget(resbar)
        self.add_widget(head)

        self.status = FLabel(text="", size_hint_y=None, height=dp(22), font_size=sp(13), color=SUB)
        self.add_widget(self.status)

        self.content = BoxLayout(orientation="vertical")
        self.add_widget(self.content)

        self.nav = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50), spacing=dp(4))
        self.nav_btns = {}
        for key, title in TABS:
            b = Button(text=title, background_normal="", background_down="",
                       background_color=MUTED, color=TEXT, font_size=sp(13))
            b.bind(on_release=lambda inst, k=key: self.show_tab(k))
            self.nav_btns[key] = b
            self.nav.add_widget(b)
        self.add_widget(self.nav)

    # ------------------------------------------------------------ жизненный цикл
    def save_path(self):
        return os.path.join(App.get_running_app().user_data_dir, "save.json")

    def start(self):
        try:
            self.game = Game.load(self.save_path())
            self.set_status("Игра загружена.", True)
            self.refresh(False)
        except Exception:
            self.game = None
            self.open_new_game(first=True)

    def persist(self):
        if self.game is None:
            return
        try:
            self.game.save(self.save_path())
        except Exception:
            pass

    # ---------------------------------------------------------------- служебное
    def set_status(self, text, ok=True):
        self.status.text = text
        self.status.color = (0.55, 0.85, 0.62, 1) if ok else (1.0, 0.55, 0.55, 1)

    def show_popup(self, title, content, size_hint=(0.92, 0.72), dismissable=True):
        p = Popup(title=title, content=content, size_hint=size_hint, auto_dismiss=dismissable,
                  title_size=sp(17), separator_color=ACCENT)
        self.popups.append(p)

        def on_dismiss(*_):
            if p in self.popups:
                self.popups.remove(p)
        p.bind(on_dismiss=on_dismiss)
        p.open()
        return p

    def info(self, title, text, button="Понятно"):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(WLabel(text=text))
        box.add_widget(sv)
        holder = {}
        box.add_widget(make_btn(button, lambda: holder["p"].dismiss()))
        holder["p"] = self.show_popup(title, box)
        return holder["p"]

    def confirm(self, text, on_yes, yes_text="Да", color=DANGER):
        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(6))
        box.add_widget(WLabel(text=text))
        holder = {}

        def yes():
            holder["p"].dismiss()
            on_yes()
        buttons = row(48)
        buttons.add_widget(make_btn("Отмена", lambda: holder["p"].dismiss(), color=MUTED))
        buttons.add_widget(make_btn(yes_text, yes, color=color))
        box.add_widget(buttons)
        holder["p"] = self.show_popup("Подтверждение", box, size_hint=(0.88, 0.38))

    def on_key(self, window, key, *args):
        """Кнопка «Назад» на Android."""
        if key == 27:
            if self.popups:
                p = self.popups[-1]
                if p.auto_dismiss:
                    p.dismiss()
                return True
            if self.tab != "cities":
                self.show_tab("cities")
                return True
        return False

    # --------------------------------------------------------------- обновление
    def show_tab(self, key):
        if self.sv is not None:
            self.scroll_pos[self.tab] = self.sv.scroll_y
        self.tab = key
        self.refresh(True)

    def refresh(self, keep_scroll=True):
        g = self.game
        if g is None:
            return
        if self.sv is not None:
            self.scroll_pos[self.tab] = self.sv.scroll_y
        self.sv = None
        self.update_header()
        for key, b in self.nav_btns.items():
            b.background_color = ACCENT if key == self.tab else MUTED
        self.content.clear_widgets()
        builder = {"cities": self.build_cities, "army": self.build_army, "map": self.build_map,
                   "diplo": self.build_diplo, "log": self.build_log}[self.tab]
        builder()
        if keep_scroll and self.sv is not None and self.tab in self.scroll_pos:
            y = self.scroll_pos[self.tab]
            Clock.schedule_once(lambda dt, sv=self.sv: setattr(sv, "scroll_y", y), 0.05)

    def update_header(self):
        g = self.game
        me = g.countries[PLAYER]
        self.name_lbl.text = me["name"]
        wars = len(g.enemies(PLAYER))
        self.info_lbl.text = "Ход %d | Городов: %d | %s" % (
            g.turn, len(g.cities_of(PLAYER)), ("Войн: %d" % wars) if wars else "мир")
        net = g.net_income(PLAYER)
        for r in RESOURCES:
            v = net[r]
            col = "7be08f" if v >= 0 else "ff7777"
            self.res_lbls[r].text = "[b]%s[/b]\n%d [color=%s]%+d[/color]" % (
                RES_NAMES[r], me["res"][r], col, v)

    def make_list(self):
        sv = ScrollView(do_scroll_x=False, bar_width=dp(4))
        grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(8), padding=[0, 0, 0, dp(8)])
        grid.bind(minimum_height=grid.setter("height"))
        sv.add_widget(grid)
        self.content.add_widget(sv)
        self.sv = sv
        return grid

    # ------------------------------------------------------------------ города
    def build_cities(self):
        g = self.game
        grid = self.make_list()
        me = g.countries[PLAYER]
        for city in g.cities_of(PLAYER):
            card = Card()
            title = city["name"] + ("  (столица)" if me["capital"] == city["id"] else "")
            card.add_widget(WLabel(text=title, bold=True, font_size=sp(17)))
            for bid in BUILD_ORDER:
                card.add_widget(self.building_row(city, bid))
            grid.add_widget(card)
        hint = Card()
        hint.add_widget(WLabel(
            text="Городов: %d из %d. Новые города основываются на свободных землях "
                 "(вкладка «Карта»). Стоимость: %s." % (
                     len(g.cities_of(PLAYER)), MAX_CITIES, fmt_cost(g.found_cost(PLAYER))),
            font_size=sp(13), color=SUB))
        grid.add_widget(hint)

    def building_row(self, city, bid):
        g = self.game
        lvl = city["b"].get(bid, 0)
        b = BUILDINGS[bid]
        r = row(64)
        r.add_widget(FLabel(
            text="[b]%s[/b]  ур. %d/%d\n[color=9aa6b8]%s[/color]" % (b["name"], lvl, MAX_LEVEL, b["desc"]),
            markup=True, font_size=sp(13)))
        if lvl >= MAX_LEVEL:
            r.add_widget(make_btn("Макс.", None, height=64, width=118, disabled=True, font=13))
        else:
            cost = g.build_cost(city["id"], bid)
            can = g.can_afford(PLAYER, cost)
            r.add_widget(make_btn("Улучшить\n" + fmt_cost(cost),
                                  lambda cid=city["id"], bb=bid: self.do_build(cid, bb),
                                  height=64, width=118, font=12, disabled=not can))
        return r

    def do_build(self, city_id, bid):
        ok, msg = self.game.build(PLAYER, city_id, bid)
        self.set_status(msg, ok)
        self.persist()
        self.refresh()

    # ------------------------------------------------------------------- армия
    def build_army(self):
        g = self.game
        me = g.countries[PLAYER]
        grid = self.make_list()
        card = Card()
        card.add_widget(WLabel(text="Ваша армия", bold=True, font_size=sp(17)))
        for u in UNIT_ORDER:
            d = UNITS[u]
            card.add_widget(WLabel(
                text="%s: [b]%d[/b]   [color=9aa6b8](атака %d, защита %d; %s)[/color]" % (
                    d["name"], me["army"][u], d["atk"], d["def"], d["note"]),
                markup=True, font_size=sp(13)))
        if any(me["returning"].values()):
            card.add_widget(WLabel(text="В походе (вернутся на следующем ходу): " + fmt_army(me["returning"]),
                                   font_size=sp(13), color=SUB))
        card.add_widget(WLabel(
            text="Всего: %d из %d | Мощь: %d | Содержание: %d еды в ход" % (
                g.army_size(PLAYER), g.army_cap(PLAYER), g.power(PLAYER), g.upkeep(PLAYER)),
            font_size=sp(13), color=SUB))
        if g.building_total(PLAYER, "barracks") <= 0:
            card.add_widget(WLabel(text="Постройте Казарму в одном из городов, чтобы нанимать войска.",
                                   font_size=sp(13), color=(1.0, 0.7, 0.4, 1)))
        grid.add_widget(card)

        for u in UNIT_ORDER:
            d = UNITS[u]
            c = Card()
            c.add_widget(WLabel(text="[b]%s[/b]  за 1: %s" % (d["name"], fmt_cost(d["cost"])),
                                markup=True, font_size=sp(14)))
            btns = row(44)
            for n in (1, 5, 10):
                cost = {k: v * n for k, v in d["cost"].items()}
                can = g.can_afford(PLAYER, cost)
                btns.add_widget(make_btn("Нанять x%d" % n,
                                         lambda uu=u, nn=n: self.do_recruit(uu, nn),
                                         height=44, font=13, disabled=not can))
            c.add_widget(btns)
            grid.add_widget(c)

    def do_recruit(self, unit, n):
        ok, msg = self.game.recruit(PLAYER, unit, n)
        self.set_status(msg, ok)
        self.persist()
        self.refresh()

    # ------------------------------------------------------------------- карта
    def build_map(self):
        g = self.game
        wrap = BoxLayout(orientation="vertical", spacing=dp(4))
        mp = RelativeLayout()
        with mp.canvas.before:
            Color(0.10, 0.17, 0.14, 1)
            bg = Rectangle(pos=(0, 0), size=mp.size)
        mp.bind(size=lambda inst, v: setattr(bg, "size", v))
        for city in g.cities.values():
            owner = city["owner"]
            if owner is None:
                col, label, name_col = (0.45, 0.47, 0.50, 1), "+", SUB
            else:
                oc = g.countries[owner]["color"]
                col = (oc[0], oc[1], oc[2], 1)
                label = str(sum(city["b"].values()))
                name_col = (1.0, 0.6, 0.6, 1) if g.at_war(PLAYER, owner) else TEXT
            b = Button(text=label, size_hint=(None, None), size=(dp(44), dp(44)),
                       pos_hint={"center_x": city["x"], "center_y": city["y"]},
                       background_normal="", background_down="", background_color=col,
                       color=(1, 1, 1, 1), font_size=sp(14), bold=True)
            b.bind(on_release=lambda inst, cid=city["id"]: self.open_city(cid))
            mp.add_widget(b)
            mp.add_widget(Label(text=city["name"], size_hint=(None, None), size=(dp(120), dp(16)),
                                pos_hint={"center_x": city["x"], "center_y": city["y"] - 0.052},
                                font_size=sp(11), color=name_col))
        wrap.add_widget(mp)
        legend = GridLayout(cols=2, size_hint_y=None, height=dp(60), row_default_height=dp(20))
        for cid, c in g.countries.items():
            txt = "[color=%s]%s[/color]%s" % (hex_color(c["color"]), c["name"],
                                              "" if c["alive"] else " (пала)")
            legend.add_widget(FLabel(text=txt, markup=True, font_size=sp(11), shorten=True))
        wrap.add_widget(legend)
        self.content.add_widget(wrap)

    def open_city(self, city_id):
        g = self.game
        city = g.cities[city_id]
        owner = city["owner"]
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        holder = {}

        def close():
            holder["p"].dismiss()

        if owner is None:
            cost = g.found_cost(PLAYER)
            box.add_widget(WLabel(text="Свободная земля. Здесь можно основать город.\nСтоимость: " + fmt_cost(cost)))
            can = g.can_afford(PLAYER, cost)

            def found():
                close()
                ok, msg = g.found_city(PLAYER, city_id)
                self.set_status(msg, ok)
                self.persist()
                self.refresh()
            box.add_widget(make_btn("Основать город", found, color=GOOD, disabled=not can))
            box.add_widget(WLabel(text="", height=dp(1)))
            box.add_widget(make_btn("Закрыть", close, color=MUTED))
            holder["p"] = self.show_popup(city["name"], box, size_hint=(0.88, 0.45))
            return

        oc = g.countries[owner]
        levels = ", ".join("%s %d" % (BUILDINGS[b]["name"], l) for b, l in city["b"].items() if l > 0)
        if owner == PLAYER:
            box.add_widget(WLabel(text="Это ваш город.\nЗдания: " + (levels or "нет")))

            def manage():
                close()
                self.show_tab("cities")
            box.add_widget(make_btn("Управлять зданиями", manage))
            box.add_widget(make_btn("Закрыть", close, color=MUTED))
            holder["p"] = self.show_popup(city["name"], box, size_hint=(0.88, 0.5))
            return

        rel = g.get_rel(PLAYER, owner)
        head = "Страна: [b]%s[/b]\nЗдания: %s" % (oc["name"], levels or "нет")
        if rel["war"]:
            box.add_widget(WLabel(text=head + "\nСостояние: [color=ff7777]ВОЙНА[/color]", markup=True))
            slider = Slider(min=10, max=100, value=80, step=5, size_hint_y=None, height=dp(44))
            prev = WLabel(font_size=sp(14), markup=True)

            def upd(*_):
                pct = int(slider.value)
                a, d, n = g.battle_preview(PLAYER, city_id, pct)
                if n == 0:
                    prev.text = "Отправить армию: %d%%. Нет войск для атаки." % pct
                    return
                ratio = a / float(max(1, d))
                if ratio >= 1.3:
                    odds = "[color=7be08f]высокие[/color]"
                elif ratio >= 0.95:
                    odds = "[color=ffd24d]примерно равные[/color]"
                else:
                    odds = "[color=ff7777]низкие[/color]"
                prev.text = ("Отправить армию: [b]%d%%[/b] (%d воинов)\nСила атаки ~%d против "
                             "обороны ~%d\nШансы: %s" % (pct, n, a, d, odds))
            slider.bind(value=upd)
            upd()
            box.add_widget(slider)
            box.add_widget(prev)

            def do_attack():
                pct = int(slider.value)
                close()
                ok, text, rep = g.attack(PLAYER, city_id, pct)
                self.persist()
                self.refresh()
                if not ok:
                    self.set_status(text, False)
                elif g.over:
                    self.show_game_over([text])
                else:
                    self.info("Результат боя", text)
            box.add_widget(make_btn("Атаковать", do_attack, color=DANGER))
            box.add_widget(make_btn("Закрыть", close, color=MUTED))
            holder["p"] = self.show_popup(city["name"], box, size_hint=(0.92, 0.7))
            return

        state = "мир" if rel["truce"] <= 0 else "перемирие (ещё %d ход.)" % rel["truce"]
        box.add_widget(WLabel(text=head + "\nСостояние: " + state, markup=True))

        def declare():
            ok, msg = g.declare_war(PLAYER, owner)
            self.set_status(msg, ok)
            self.persist()
            self.refresh()
            if ok:
                self.open_city(city_id)

        def ask():
            close()
            self.confirm("Объявить войну «%s»?" % oc["name"], declare, "Объявить войну")
        box.add_widget(make_btn("Объявить войну", ask, color=DANGER, disabled=rel["truce"] > 0))
        box.add_widget(make_btn("Закрыть", close, color=MUTED))
        holder["p"] = self.show_popup(city["name"], box, size_hint=(0.88, 0.5))

    # ------------------------------------------------------------------- страны
    def build_diplo(self):
        g = self.game
        grid = self.make_list()
        mine = Card()
        mine.add_widget(WLabel(text="Ваша мощь: %d | Городов: %d" % (
            g.power(PLAYER), len(g.cities_of(PLAYER))), font_size=sp(14)))
        grid.add_widget(mine)
        for cid, c in g.countries.items():
            if cid == PLAYER:
                continue
            card = Card()
            col = hex_color(c["color"])
            if not c["alive"]:
                card.add_widget(WLabel(text="[color=%s]%s[/color]  - пала" % (col, c["name"]),
                                       markup=True, font_size=sp(14), color=SUB))
                grid.add_widget(card)
                continue
            rel = g.get_rel(PLAYER, cid)
            if rel["war"]:
                state = "[color=ff7777]ВОЙНА[/color]"
            elif rel["truce"] > 0:
                state = "перемирие (ещё %d)" % rel["truce"]
            else:
                state = "мир"
            others = [g.countries[o]["name"] for o in g.enemies(cid) if o != PLAYER]
            extra = ("\nВоюет с: " + ", ".join(others)) if others else ""
            card.add_widget(WLabel(
                text="[b][color=%s]%s[/color][/b]\nГородов: %d | Мощь: %d | %s%s" % (
                    col, c["name"], len(g.cities_of(cid)), g.power(cid), state, extra),
                markup=True, font_size=sp(14)))
            if cid in g.offers:
                card.add_widget(make_btn("Принять мир", lambda x=cid: self.do_accept(x), color=GOOD, height=44))
            if rel["war"]:
                card.add_widget(make_btn("Предложить мир", lambda x=cid: self.do_peace(x), height=44))
            else:
                card.add_widget(make_btn("Объявить войну", lambda x=cid: self.ask_war(x),
                                         color=DANGER, height=44, disabled=rel["truce"] > 0))
            grid.add_widget(card)

    def do_accept(self, cid):
        ok, msg = self.game.accept_offer(cid)
        self.set_status(msg, ok)
        self.persist()
        self.refresh()

    def do_peace(self, cid):
        ok, msg = self.game.propose_peace(cid)
        self.set_status(msg, ok)
        self.persist()
        self.refresh()

    def ask_war(self, cid):
        name = self.game.countries[cid]["name"]

        def go():
            ok, msg = self.game.declare_war(PLAYER, cid)
            self.set_status(msg, ok)
            self.persist()
            self.refresh()
        self.confirm("Объявить войну «%s»?" % name, go, "Объявить войну")

    # ------------------------------------------------------------------ журнал
    def build_log(self):
        grid = self.make_list()
        card = Card()
        lines = list(reversed(self.game.log[-80:]))
        card.add_widget(WLabel(text="\n\n".join(lines) if lines else "Пока пусто.", font_size=sp(13)))
        grid.add_widget(card)

    # --------------------------------------------------------------- ход и итоги
    def end_turn(self):
        g = self.game
        if g is None:
            return
        if g.over:
            self.show_game_over([])
            return
        done = g.turn
        msgs = g.end_turn()
        self.persist()
        self.refresh(True)
        if g.over:
            self.show_game_over(msgs)
        else:
            self.info("Ход %d завершён" % done, "\n\n".join(msgs) if msgs else "Ничего не произошло.",
                      "Дальше")

    def show_game_over(self, msgs):
        g = self.game
        win = g.over == "win"
        text = "\n\n".join(msgs)
        if g.over is None:
            return
        text += ("\n\n" if text else "") + (
            "Поздравляем! Все города соперников под вашим флагом." if win
            else "Ваша империя пала. Попробуйте снова!")
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(WLabel(text=text))
        box.add_widget(sv)
        holder = {}

        def again():
            holder["p"].dismiss()
            self.open_new_game()
        btns = row(48)
        btns.add_widget(make_btn("Смотреть карту", lambda: holder["p"].dismiss(), color=MUTED))
        btns.add_widget(make_btn("Новая игра", again, color=GOOD))
        box.add_widget(btns)
        holder["p"] = self.show_popup("ПОБЕДА!" if win else "ПОРАЖЕНИЕ", box)

    # --------------------------------------------------------------------- меню
    def open_menu(self):
        if self.game is None:
            return
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        holder = {}

        def close():
            holder["p"].dismiss()

        def save():
            close()
            self.persist()
            self.set_status("Игра сохранена.", True)

        def new():
            close()
            self.confirm("Начать новую игру? Текущая партия будет потеряна.",
                         lambda: self.open_new_game(), "Начать", GOOD)

        def howto():
            close()
            self.info("Как играть", HELP_TEXT)
        box.add_widget(make_btn("Сохранить игру", save))
        box.add_widget(make_btn("Как играть", howto, color=MUTED))
        box.add_widget(make_btn("Новая игра", new, color=MUTED))
        box.add_widget(make_btn("Закрыть", close, color=MUTED))
        holder["p"] = self.show_popup("Меню", box, size_hint=(0.8, 0.5))

    def open_new_game(self, first=False):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        box.add_widget(WLabel(text="Название вашей страны:"))
        name = TextInput(text="Моя империя", multiline=False, size_hint_y=None, height=dp(44),
                         font_size=sp(16))
        box.add_widget(name)
        box.add_widget(WLabel(text="Сложность соперников:"))
        diff_row = row(44)
        diff_btns = []
        for i, title in enumerate(DIFFICULTY_NAMES):
            tb = ToggleButton(text=title, group="difficulty", allow_no_selection=False,
                              background_normal="", background_down="", font_size=sp(14),
                              state="down" if i == 1 else "normal",
                              background_color=ACCENT if i == 1 else MUTED, color=TEXT)
            tb.bind(state=lambda inst, st: setattr(inst, "background_color",
                                                   ACCENT if st == "down" else MUTED))
            diff_btns.append(tb)
            diff_row.add_widget(tb)
        box.add_widget(diff_row)
        if first:
            box.add_widget(WLabel(text="Подсказка: меню (кнопка вверху) содержит правила игры.",
                                  font_size=sp(12), color=SUB))
        holder = {}

        def start():
            level = 1
            for i, tb in enumerate(diff_btns):
                if tb.state == "down":
                    level = i
            holder["p"].dismiss()
            self.game = Game()
            self.game.new_game(name.text, level)
            self.tab = "cities"
            self.scroll_pos = {}
            self.persist()
            self.set_status("Новая игра начата. Удачи, правитель!", True)
            self.refresh(False)
        box.add_widget(make_btn("Начать игру", start, color=GOOD))
        holder["p"] = self.show_popup("Новая игра", box, size_hint=(0.9, 0.6), dismissable=not first)


class EmpireApp(App):
    title = "Строй Империю"

    def build(self):
        if platform not in ("android", "ios"):
            Window.size = (405, 810)
        Window.clearcolor = BG
        self.main = Root()
        Window.bind(on_keyboard=self.main.on_key)
        return self.main

    def on_start(self):
        self.main.start()

    def on_pause(self):
        self.main.persist()
        return True

    def on_stop(self):
        self.main.persist()


if __name__ == "__main__":
    EmpireApp().run()
