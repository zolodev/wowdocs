#!/usr/bin/env python3
"""Build site/icons-index.js from a folder of WoW icon PNGs.

Each icon gets its file name, size in bytes, image size and a set of automatic
groups guessed from Blizzard's naming patterns (INV_Sword_04, Spell_Fire_Fireball,
Ability_Warrior_Charge, Trade_Alchemy, Achievement_Character_Human_Female …).
Manual tags are not stored here; they live in site/icon-tags.jsonl.

Usage:
    python3 tools/build_icons.py [path/to/png]

Default path: png/ in this repo.
"""
import json
import pathlib
import re
import struct
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PNG = SITE / "png"
OUT = SITE / "icons-index.js"

CLASSES = {
    "Warrior": r"warrior", "Paladin": r"paladin", "Hunter": r"(?<!demon)(?<!demon_)hunter", "Rogue": r"rogue",
    "Priest": r"priest", "Death Knight": r"death_?knight|^spell_deathknight", "Shaman": r"shaman",
    "Mage": r"(^|_)mage", "Warlock": r"warlock", "Monk": r"(^|_)monk", "Druid": r"druid",
    "Demon Hunter": r"demon_?hunter", "Evoker": r"evoker",
}
RACES = {
    "Human": r"human", "Dwarf": r"dwarf", "Night Elf": r"night_?elf", "Gnome": r"(?<!mecha)gnome",
    "Draenei": r"draenei", "Worgen": r"worgen", "Orc": r"(^|_)orc(_|$)|_orc", "Troll": r"(^|_)troll",
    "Tauren": r"tauren", "Undead": r"undead|forsaken|scourge", "Blood Elf": r"blood_?elf",
    "Goblin": r"goblin", "Pandaren": r"pandaren", "Nightborne": r"nightborne", "Void Elf": r"void_?elf",
    "Vulpera": r"vulpera", "Mechagnome": r"mechagnome", "Dracthyr": r"dracthyr", "Earthen": r"earthen",
}

# (group, pattern on the lower-case file name without .png). An icon can be in
# several groups. Edit these to change the automatic grouping.
GROUPS = [
    ("Items", r"^(inv|ivn|item)"),
    ("Spells", r"^(spell|ability|artifactability|sha_|buff)"),
    ("Achievements", r"^achi[e]?v"),
    ("Professions", r"^(trade|tradeskill|10prof|70_inscription)|profession|alchemy|blacksmith|enchanting|"
                    r"engineering|herbalism|inscription|jewelcraft|leatherwork|mining|skinning|tailoring|"
                    r"cooking|fishing|archaeology|firstaid"),
    ("Class", r"classicon|talentspec|" + "|".join(CLASSES.values())),
    ("Character", r"achievement_character|racial|(^|_)(fe)?male(_|$)|" + "|".join(RACES.values())),
    ("Factions", r"reputation|faction|banner|tabard|alliance|horde|(^|_)argent|kirin_?tor|cenarion|"
                 r"ebon_?blade|shattrath|aldor|scryer"),
    ("Mounts", r"mount"),
    ("Pets", r"(^|_)pet(_|s|$)|petbattle|battlepet|companion|hunter_pet"),
    ("Bosses", r"(^|_)boss|creatureportrait|raidability|^6bf|highmaulraid|^10_2_raid"),
    ("Raids & dungeons", r"(^|_)raid|dungeon|(^|_)instance|challengemode|mythic|^achievement_zone"),
    ("PvP", r"pvp|arena|battleground|honor|(^|_)bg_"),
    ("UI", r"^(ui|icon|garrison|expansionicon|wow_)"),
    # Spell schools (spells only, see SPELL_ONLY).
    ("Fire", r"^spell_fire|fire"),
    ("Frost", r"^spell_frost|frost|(^|_)ice"),
    ("Nature", r"^spell_nature"),
    ("Shadow", r"^spell_shadow|shadow"),
    ("Holy", r"^spell_holy|(?<!un)holy"),  # not "Unholy" (Death Knight)
    ("Arcane", r"^spell_arcane|arcane"),
    # Item types (items only, see ITEM_ONLY).
    ("Weapons", r"sword|(^|_)axe|mace|staff|stave|(^|_)bow|(^|_)gun|rifle|dagger|polearm|spear|wand|"
                r"(^|_)fist|glaive|crossbow|thrown|hammer|weapon|knife|warglaive"),
    ("Shields", r"shield"),
    ("Armor", r"helm|chest|shoulder|boot|gauntlet|glove|(^|_)hands?(_|$)|belt|pant|bracer|cloak|(^|_)cape|"
              r"shirt|robe|(^|_)legs?(_|$)|legging|wrist|waist|armor|plate|(^|_)mail|cloth_|leather_|bracer"),
    ("Jewelry", r"(^|_)ring|necklace|(^|_)neck|jewelry|trinket|amulet|earring"),
    ("Gems", r"gem(?!ini)|jewel(?!craft)"),
    ("Consumables", r"potion|elixir|flask|(^|_)food|drink|bread|meat|cheese|fruit|mushroom|scroll|"
                    r"bandage|feast|(^|_)ale|wine"),
    ("Materials", r"(^|_)herb|(^|_)ore|(^|_)bar_|ingot|fabric|(^|_)hide|(^|_)dust|essence|shard|"
                  r"(^|_)leather(_|$)|(^|_)cloth(_|$)|reagent"),
    ("Books", r"(^|_)book|tome|(^|_)note"),
    ("Containers", r"(^|_)bag|(^|_)box|satchel|pouch|(^|_)crate|lockbox"),
    ("Keys", r"(^|_)key"),
    ("Food & drink", r"(^|_)food|drink|bread|meat|cheese|fruit|feast|(^|_)ale|wine|(^|_)fish(_|$)"),
]
SPELL_ONLY = {"Fire", "Frost", "Nature", "Shadow", "Holy", "Arcane"}

# How the icon browser lays out the group filters: one row per category, groups in
# this order. Groups not listed here end up in an "Other" row.
CATEGORIES = [
    ("Type", ["Items", "Spells", "Class abilities", "Achievements", "Mounts", "Pets", "Professions", "UI", "Retail"]),
    ("Classes", ["Class", "Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Shaman", "Mage", "Warlock",
                 "Druid", "Death Knight", "Monk", "Demon Hunter", "Evoker"]),
    ("Races", ["Character", "Human", "Dwarf", "Night Elf", "Gnome", "Draenei", "Worgen", "Void Elf",
               "Mechagnome", "Orc", "Undead", "Tauren", "Troll", "Blood Elf", "Goblin", "Nightborne",
               "Vulpera", "Pandaren", "Dracthyr", "Earthen"]),
    ("Spell schools", ["Fire", "Frost", "Nature", "Shadow", "Holy", "Arcane"]),
    ("Item types", ["Weapons", "Shields", "Armor", "Jewelry", "Gems", "Consumables", "Food & drink",
                    "Materials", "Containers", "Books", "Keys"]),
    ("Factions & PvP", ["Factions", "Alliance", "Horde", "PvP"]),
    ("Encounters", ["Bosses", "Raids & dungeons"]),
]
# Shorter, clearer labels for a few groups in the filter rows.
LABELS = {"Class": "Any class", "Character": "Any race"}
NOT_ITEM = {"Raids & dungeons"}  # gear sets are often named "Raid…", so items are skipped
ITEM_ONLY = {"Weapons", "Shields", "Armor", "Jewelry", "Gems", "Consumables", "Materials",
             "Books", "Containers", "Keys", "Food & drink"}


# "Retail": icons that are clearly newer than Classic, judged by the file name only.
# Everything else is left unsorted (it may or may not exist in Classic / WoW Forever).
CLASS_SPELL = re.compile(
    r"^(ability|spell|inv_ability|inv_spell)_(warrior|paladin|hunter|rogue|priest|shaman|mage|warlock|druid|racial)")

# Single icons you decided are Retail: later spells no name rule catches, and icons
# that are Retail even though a WoW Forever ability uses them. Wins over everything.
RETAIL_BY_CHOICE = {
    "ability_mount_camel_brown",   # Camel mount (Cataclysm)
    "ability_druid_nourish",       # Nourish (Wrath)
    "ability_druid_lunarguidance",
    "ability_mage_frostfirebolt",  # Frostfire Bolt (Wrath)
    "spell_fire_blueflamebolt",
    "ability_mage_frostjaw",       # Frostjaw (Mists of Pandaria)
    "spell_firefrost orb",         # Frostfire Orb (Cataclysm)
    "spell_frost_arcticwinds",     # Arctic Winds (Wrath)
    "spell_frost_chainsofice",     # Chains of Ice (Death Knight, Wrath)
    "spell_frost_coldhearted",
    "spell_frost_frozencore",
    "spell_frost_frozenorb",       # Frozen Orb (Cataclysm)
    "spell_frost_glacier",
    "spell_frost_icefloes",        # Ice Floes (Mists of Pandaria)
    "spell_frost_iceshard",
    "spell_frost_iceshock",
    "spell_frost_manarecharge",
    "spell_frost_piercing chill",
    "spell_frost_ring of frost",   # Ring of Frost (Cataclysm)
    "spell_frost_summonwaterelemental",    # Summon Water Elemental (The Burning Crusade)
    "spell_frost_summonwaterelemental_2",
    "spell_frost_wisp",
    "spell_ice_lament",            # Icy Veins (The Burning Crusade)
    "spell_ice_rune",
    "spell_nature_sicklypolymorph",
}

# Achievements (added in Wrath), classes and races that don't exist in Classic / WoW Forever,
# and allied races: always Retail, even when a Forever ability reuses the icon.
ALWAYS_RETAIL = re.compile(
    r"^achi?e?v|achievement|death_?knight|_dk(_|mount|whelpling|$)|demon_?hunter|monk(?!ey)|evoker|alliedrace|draenei|blood_?elf|worgen|goblin|pandaren|"
    r"nightborne|void_?elf|vulpera|mechagnome|dracthyr|earthen|earten|lightforged|highmountain|zandalari|"
    r"kul_?tiran|maghar|darkiron")

RETAIL = [
    r"^(inv_?\d{2,3}[_\d]|\d|inv12)",                             # expansion/patch number: INV_10_, 70_, 6BF_ …
    r"^achi?e?v",                                                  # achievements (added in Wrath)
    r"^ability_pvp_",                                              # PvP abilities and talents (Wrath and later)
    r"fel_?lord|^ability_boss|^ability_[a-z]+_boss|gorefiend|fomor|highmaul|blackrock_?foundry|hellfire_?citadel",  # raids (Warlords and later)
    r"odun|odyn",                                                  # Odyn and his runes (Legion)
    r"^creatureportrait",                                          # vehicle / creature action icons (Wrath and later)
    r"summonable|token_boost|^wow_token|honor_?hold|thrallmar",   # boss tokens, boosts, WoW Token, TBC factions
    r"^sha_",                                                      # Sha / Nightborne / Nightmare recolours (Pandaria, Legion)
    r"carpet|frostwyrm|protodragon",                               # flying carpets (Wrath), frostwyrms, proto-dragons
    r"frostfire",                                                  # Frostfire spells and zones (Wrath and later)
    # Interface icons for later systems. General ones (professions, chat, shop,
    # self-found, faction icons …) stay, since WoW Forever's interface may use them.
    r"^ui_(followerdungeon|majorfaction|embercourt|endeavor|lemix|plunder|prey|notoriety|abundance|"
    r"homestone|concentration|campcollection|sigil|warmode|darkshore_warfront|promotion|"
    r"resourcelumber(?!vanilla)|mission_|horde_honorbound|calendar_)",
    r"monk(?!ey)|death_?knight|demon_?hunter|evoker|^spell_deathknight", # classes added after Classic
    r"draenei|blood_?elf|worgen|goblin|pandaren|nightborne|void_?elf|vulpera|mechagnome|"
    r"dracthyr|earthen|lightforged|highmountain|zandalari|kul_?tiran|maghar|darkiron",  # races added after Classic
    r"garrison|artifact|azerite|covenant|soulbind|anima|housing|warband|delve|torghast|legion|"
    r"draenor|pandaria|shadowlands|dragonflight|zuldazar|nazjatar|mechagon|ardenweald|bastion|"
    r"maldraxxus|revendreth|(^|_)maw(_|$)|timerunning|dragon_?riding|sky_?riding|argus",  # later systems and zones
    # Zones, raids, factions and characters from The Burning Crusade and later.
    # (Hyjal and Dalaran are left out: both exist in WoW Forever / vanilla.)
    r"ethereal|outland|sunwell|aldor|naaru|netherwing|hellfire|karazhan|kael|fel_?orc|shattrath|netherstorm|"
    r"nagrand|illidan|magtheridon|shatar|vashj",                                       # The Burning Crusade
    r"valkyr|icecrown|northrend|ulduar|wintergrasp|lich_?king|sindragosa|arthas|yogg",    # Wrath of the Lich King
    r"cataclysm|firelands|deathwing|gilneas|uldum|tol_?barad|vashjir|tol_?vir",           # Cataclysm
    r"nerubian|kul_?tiras|oribos|nzoth|zandalar|undermine|mantid|thunder_?king|mogu|garrosh|antorus|"
    r"suramar|valdrakken|shado_?pan|broken_?isles|ashran|deepwind|kotmogu|silvershard|progenitor",  # Pandaria and later
]


WEAPON_TYPES = {"sword", "mace", "staff", "stave", "axe", "weapon", "knife", "polearm", "bow", "wand",
                "glaive", "hammer", "firearm", "crossbow", "spear", "throwingknife", "thrown", "gun", "dagger"}


def item_type(name):
    """First word after INV_ / INV_10_ …, e.g. "inv_sword_04" -> "sword"."""
    m = re.match(r"^(?:inv|ivn)_?(?:\d+_)*([a-z]+)", name)
    return m.group(1) if m else ""


def groups_for(stem):
    name = stem.lower()
    is_spell = re.match(r"^(spell|ability|artifactability|sha_|buff)", name) is not None
    is_item = re.match(r"^(inv|ivn|item)", name) is not None
    found = []
    for group, pattern in GROUPS:
        if group in SPELL_ONLY and not is_spell:
            continue
        if group in ITEM_ONLY and not is_item:
            continue
        if group in NOT_ITEM and is_item:
            continue
        if re.search(pattern, name):
            found.append(group)
    # Class from the file name only for spells and abilities: an item such as a tier
    # set piece ("…RaidPriest…") isn't one of the class's spells.
    if is_item:
        found = [g for g in found if g != "Class"]
    else:
        for cls, pattern in CLASSES.items():
            if re.search(pattern, name):
                found.append(cls)
    # Race, like class, only for spells and abilities: "…BloodElfCrafting…" on a
    # weapon is an item, not a racial.
    if is_item:
        found = [g for g in found if g != "Character"]
    else:
        for race, pattern in RACES.items():
            if re.search(pattern, name):
                found.append(race)
    # An item can match both weapon and armor words ("INV_Tabard_…VoljinsSpear",
    # "…TwilightHammer…"). The first word after INV_ is the item's type in Blizzard's
    # names, so a weapon type there makes it a weapon; otherwise armor words win.
    if is_item and "Weapons" in found and "Armor" in found:
        found.remove("Armor" if item_type(name) in WEAPON_TYPES else "Weapons")
    if is_item and "Weapons" in found and re.search(r"tabard|shirt", name):
        found.remove("Weapons")
        if "Armor" not in found:
            found.append("Armor")
    # "Cloth"/"Leather" on gear is the armor type, not a crafting material.
    if "Materials" in found and ("Armor" in found or "Weapons" in found):
        found.remove("Materials")
    if "alliance" in name:
        found.append("Alliance")
    if "horde" in name:
        found.append("Horde")
    # Flying mounts came with The Burning Crusade (carpets and drakes with Wrath).
    if "Mounts" in found and re.search(r"flying|carpet|drake|wyrm|serpent|nether_?ray", name):
        found.append("Retail")
    if any(re.search(pattern, name) for pattern in RETAIL):
        found.append("Retail")
    return found


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    return (0, 0)


ALL_CLASSES = set(CLASSES)
ALL_RACES = set(RACES)
CLASS_ICONS = SITE / "class-icons.json"  # icons used by each class's spells and skills in WoW Forever


def class_icons():
    """icon name (lower case) -> {"classes": [...], "races": [...]}; empty if the file isn't there."""
    if not CLASS_ICONS.exists():
        return {}
    return json.loads(CLASS_ICONS.read_text(encoding="utf-8"))["icons"]


EQUIPMENT = {"Armor", "Weapons", "Shields", "Jewelry"}

# Icons WoW Forever's own spells and items use (tools/build_forever_icons.py).
# Every other icon belongs to a later expansion: Retail.
FOREVER_ICONS = SITE / "forever-icons.txt"
# Interface icons that no spell or item uses but that belong to Classic / WoW Forever.
FOREVER_INTERFACE = re.compile(
    r"^(expansionicon_classic|ui_allianceicon|ui_hordeicon|ui_chat|ui_greenflag|ui_selffound|ui_profession_)")


def forever_icons():
    """Lower-case names of the icons WoW Forever uses; empty if the file isn't there."""
    if not FOREVER_ICONS.exists():
        return set()
    lines = FOREVER_ICONS.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def apply_class_icons(groups, used, all_classes):
    """For icons a class's spells and skills use, that data wins over guesses from the
    file name: its classes (and races, for racial skills) are set, and it isn't Retail.

    Skills every class has (armor and weapon proficiencies and the like) and equipment
    icons don't count as the class's own: those icons only lose "Retail"."""
    groups = [g for g in groups if g != "Retail"]
    if set(used["classes"]) >= all_classes or EQUIPMENT & set(groups):
        return groups
    # Items stay out of the race groups even when a racial skill uses their icon.
    races = [] if "Items" in groups else used.get("races", [])
    groups = [g for g in groups if g not in ALL_CLASSES]
    if races:
        groups = [g for g in groups if g not in ALL_RACES]
    groups += ["Spells", "Class abilities", "Class", *used["classes"]]
    if races:
        groups += ["Character", *races]
    return list(dict.fromkeys(groups))


def main():
    folder = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PNG
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".png")
    if not files:
        sys.exit(f"No .png files in {folder}")

    group_names, group_index, icons = [], {}, []
    counts = {}
    used_by_classes = class_icons()
    forever_classes = {c for used in used_by_classes.values() for c in used["classes"]}
    used_by_forever = forever_icons()
    for path in files:
        indexes = []
        groups = groups_for(path.stem)
        if path.stem.lower() in used_by_classes:
            groups = apply_class_icons(groups, used_by_classes[path.stem.lower()], forever_classes)
        # Later classes and races don't exist in Classic / WoW Forever: always Retail.
        stem = path.stem.lower()
        # A spell icon named after a Classic class ("Ability_Mage_…", "Spell_Priest_…") or a
        # racial ("Ability_Racial_…") that no WoW Forever ability uses is a later talent,
        # spell or race's racial.
        if used_by_classes and CLASS_SPELL.match(stem) and stem not in used_by_classes and "Retail" not in groups:
            groups.append("Retail")
        if (ALWAYS_RETAIL.search(stem) or stem in RETAIL_BY_CHOICE) and "Retail" not in groups:
            groups.append("Retail")
        if (used_by_forever and stem not in used_by_forever and stem not in used_by_classes
                and not FOREVER_INTERFACE.match(stem) and "Retail" not in groups):
            groups.append("Retail")
        for group in groups:
            if group not in group_index:
                group_index[group] = len(group_names)
                group_names.append(group)
            indexes.append(group_index[group])
            counts[group] = counts.get(group, 0) + 1
        w, h = png_size(path)
        icons.append([path.name, path.stat().st_size, w, h, indexes])

    data = {"folder": "png/", "groups": group_names, "icons": icons,
            "categories": [[name, [g for g in groups if g in group_index]] for name, groups in CATEGORIES],
            "labels": LABELS}
    OUT.write_text(
        "// Generated by tools/build_icons.py. Do not edit.\n"
        "// icons: [file name, bytes, width, height, [group indexes]]\n"
        "window.ICON_INDEX = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    ungrouped = sum(1 for icon in icons if not icon[4])
    print(f"{len(icons)} icons -> {OUT} ({OUT.stat().st_size // 1024} KB), {ungrouped} without a group")
    print(", ".join(f"{g} {c}" for g, c in sorted(counts.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
