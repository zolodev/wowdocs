#!/usr/bin/env python3
"""Build site/reference-data.js from the wow-forever-addon-dev API reference.

The reference is Markdown generated from Blizzard_APIDocumentationGenerated
(wow-ui-source, branch "forever"). This turns it into one compact data file that
reference.html searches locally in the browser.

Usage:
    python3 tools/build_reference.py [path/to/references]

Default path: ~/.claude/skills/wow-forever-addon-dev/references
"""
import json
import pathlib
import re
import sys

DEFAULT_REFS = pathlib.Path.home() / ".claude/skills/wow-forever-addon-dev/references"
OUT = pathlib.Path(__file__).resolve().parent.parent / "reference-data.js"

TABLE_KINDS = {
    "Enumeration": "enum",
    "Structure": "struct",
    "Constants": "const",
    "CallbackType": "callback",
}

HEADER = re.compile(
    r"(?:Namespace: `(?P<ns>[^`]+)`|Global functions \(no namespace\))"
    r" · Type: (?P<type>\w+) · Environment: (?P<env>\w+)"
)
ENTRY = re.compile(r"^### (?P<name>\S+)(?: \((?P<kind>[^)]+)\))?$")
PREDICATE = re.compile(r"^- `(?P<name>[^`]+)` \((?P<kind>[^)]+)\)\s*(?P<rest>.*)$")

# ── Tags ──────────────────────────────────────────────────────────────────────
# Topic tags come from the system's name. A system can get several tags.
# Edit these to change how the reference is grouped.
SYSTEM_TAGS = [
    ("UI", r"^Simple(?!(Object|FrameScriptObjectConstants)$)|^FrameAPI|Frame|Tooltip|Font|Texture|"
           r"Minimap|NamePlate|Model|Scene|Cursor|EditMode|UI$|UIShared|UIConstants|UITypes|UIInternal|"
           r"^UI|^Ui|Widget|ColorUtil|^Screen$|^Movie$|^Browser$|TalkingHead|SplashScreen|LoadingScreen|"
           r"ChatBubbles|CombatText|ActionBar|CooldownViewer|SpellActivationOverlay|XMLUtil|SettingsUtil|"
           r"KeyBindings|ClickBindings|GameUI|GamepadUI|SocialUI|AuraContainer|TextureUtils"),
    ("Unit", r"^Unit|CreatureInfo|PlayerInfo|PartyInfo|UnitRole|Vehicle|IncomingSummon|SummonInfo"),
    ("Combat", r"CombatLog|Threat|SwingTimer|DamageMeter|LossOfControl|SpellDiminish|DeathRecap|DeathInfo|"
               r"DeathAlert|AssistedCombat|EncounterWarnings|CombatAudioAlert|Totem"),
    ("Spell", r"^Spell|Talent|Trait|Specialization|ClassTalents|Glyph|ZoneAbility|SharedTraits"),
    ("Item", r"^Item|Container|^Bag|^Bank|^Loot|EquipmentSet|NewItems|Azerite|AutoLoot|QuestItemUse"),
    ("Map", r"^Map|Minimap|TaxiMap|AreaPoi|Vignette|FogOfWar|SuperTrack|InGameNavigation|AdventureMap|"
            r"UIMapPin|MapExploration|WorldState|PlayerLocation"),
    ("Quest", r"^Quest|Gossip|TaskInfo|ContentTracking|PlayerChoice|WarCampaign|WeeklyRewards"),
    ("Social", r"^Chat|^Club|BattleNet|FriendList|^Guild|^Party|SocialQueue|VoiceChat|MailInfo|"
               r"RecruitAFriend|RecentAllies|^Ping|Social|ReportSystem|AutoComplete"),
    ("PvP", r"Pvp|PvP|PVP|Duel"),
    ("Group finder", r"^LFG|LobbyMatchmaker|QueueSpecific"),
    ("Instances", r"Instance|Encounter|Dungeon|MythicPlus|ChallengeMode|Scenario|Delves|RaidLocks|Islands|"
                  r"RaidMarker"),
    ("Collections", r"Mount|PetJournal|ToyBox|Heirloom|Transmog|^Title$|AppearanceSource|DyeColor|"
                    r"WarbandScene"),
    ("Auction House", r"AuctionHouse"),
    ("Economy", r"AuctionHouse|Merchant|^Trade|Currency|Money|BlackMarket|WowToken|CatalogShop|Store|"
                r"AccountStore|SecureTransfer|Perks"),
    ("Professions", r"TradeSkill|Profession|CraftingOrder|SkillInfo"),
    ("Housing", r"Housing|^House|Neighborhood"),
    ("Pets", r"BattlePet|PetBattle|^Pet|StableInfo"),
    ("Achievements", r"Achievement"),
    ("Character", r"PaperDoll|BarberShop|Character|AlliedRaces|Covenant|Soulbinds|Renown|MajorFactions|"
                  r"Reputation|Expansion|LevelSquish"),
    ("System", r"^AddOn|CVar|Console|^Client|^Build$|^Os$|Platform|SystemInfo|Locale|Localization|^Intl|"
               r"^Lua|^String|EncodingUtil|EventUtils|FrameScript|SecretUtil|SecretPredicates|RestrictedActions|"
               r"GameRules|^Input|GamePad|SlashCommand|DateAndTime|SystemTime|^Time$|Sound|Camera|Video|Streaming"),
]

# Types that mean "this touches the UI" when a function takes or returns them.
UI_TYPES = {
    "ScriptRegion", "SimpleFrame", "SimpleRegion", "SimpleTexture", "SimpleFontString", "SimpleFont",
    "SimpleLine", "SimpleAnimGroup", "SimpleAnim", "SimpleButton", "SimpleEditBox", "SimpleStatusBar",
    "FramePoint", "FrameStrata", "DrawLayer", "uiUnit", "textureAtlas", "TextureAsset", "TextureKit",
    "textureKit", "uiFontHeight", "JustifyHorizontal", "JustifyVertical", "ScriptTypeName", "BlendMode",
}
# Flags meaning the entry can return (or an event can carry) secret values.
# "SecretArguments=..." alone only limits what you may pass in, so it doesn't count.
SECRET_VALUES = re.compile(r"SecretReturns|SecretWhen|SecretIn[A-Z]|SecretOn[A-Z]|SecretPayloads")
TYPE_NAME = re.compile(r"`[^`]+`:\s*([A-Za-z_][A-Za-z0-9_]*)")


# Systems whose names match a pattern above but that aren't about that topic.
NOT_TAGGED = {
    "UI": {"FrameScript", "WarbandSceneInfo", "WarbandSceneInfoConstants"},
}


def system_tags(name):
    return [tag for tag, pattern in SYSTEM_TAGS
            if research(pattern, name) and name not in NOT_TAGGED.get(tag, ())]


# Topic tags for single entries in other systems: (tag, parameter text, event name).
# A function or structure gets the tag when one of its parameters/fields matches;
# an event gets it when its name matches.
ENTRY_TAGS = [
    ("Map", r"`(ui)?[mM]apID`|\bUiMap\w*", r"^(ZONE_CHANGED|MAP_|NEW_WMO|WORLD_MAP)"),
    ("Auction House", r"\bAuctionHouse\w*|`itemKey`", r"^AUCTION_"),
]


def entry_tags(entry, tags_of_system, env):
    """Tags for one entry: its system's topics, UI/Map/Auction House by parameters
    or event name, and flags."""
    tags = list(tags_of_system)
    items = entry.get("items", [])
    is_event = entry["k"] == "event"
    if "UI" not in tags:
        types = {m.group(1) for item in items for m in [TYPE_NAME.search(item)] if m}
        if types & UI_TYPES or (is_event and entry["n"].startswith("UI_")):
            tags.append("UI")
    for tag, item_pattern, event_pattern in ENTRY_TAGS:
        if tag in tags:
            continue
        if (is_event and re.search(event_pattern, entry["n"])) or \
                any(re.search(item_pattern, item) for item in items):
            tags.append(tag)
    flags = entry.get("flags", "")
    if SECRET_VALUES.search(flags):
        tags.append("Secret")
    if "IsProtectedFunction" in flags:
        tags.append("Protected")
    if env == "SecureOnly":
        tags.append("SecureOnly")
    return tags


def parse_system(path, system_index):
    """Returns (system, entries) for one api/*.md file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    name = lines[0].removeprefix("# ").strip()
    header = HEADER.search(lines[2]) if len(lines) > 2 else None
    system = {
        "name": name,
        "ns": header["ns"] if header and header["ns"] else "",
        "type": header["type"] if header else "",
        "env": header["env"] if header else "",
        "file": path.name,
    }
    is_widget = system["type"] == "ScriptObject"

    entries, section, current = [], None, None

    def finish():
        if current:
            entries.append(current)

    for line in lines[3:]:
        if line.startswith("## "):
            finish()
            current = None
            section = line[3:].split(" ")[0]  # Functions, Events, Tables, Predicates
            continue

        match = ENTRY.match(line)
        if match:
            finish()
            if section == "Functions":
                kind = "method" if is_widget else "function"
            elif section == "Events":
                kind = "event"
            else:
                kind = TABLE_KINDS.get(match["kind"] or "", "table")
            current = {"k": kind, "n": match["name"], "s": system_index,
                       "sig": "", "doc": [], "flags": "", "items": []}
            continue

        if section == "Predicates":
            match = PREDICATE.match(line)
            if match:
                entries.append({"k": "predicate", "n": match["name"], "s": system_index,
                                "sig": "", "doc": [match["kind"]],
                                "flags": match["rest"].strip(), "items": []})
            continue

        if current is None or not line.strip():
            continue
        if line.startswith("`") and not current["sig"] and not current["items"]:
            current["sig"] = line.strip("`")
        elif line.startswith("Flags: "):
            current["flags"] = line[len("Flags: "):]
        elif line.startswith("- "):
            current["items"].append(line[2:])
        else:
            current["doc"].append(line)
    finish()

    system["tags"] = system_tags(name)
    for entry in entries:
        entry["t"] = entry_tags(entry, system["tags"], system["env"])

    # Drop empty fields to keep the file small.
    for entry in entries:
        for key in ("sig", "doc", "flags", "items", "t"):
            if not entry[key]:
                del entry[key]
        if "doc" in entry:
            entry["doc"] = " ".join(entry["doc"])
    return system, entries


def main():
    refs = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REFS
    files = sorted((refs / "api").glob("*.md"))
    if not files:
        sys.exit(f"No api/*.md files in {refs}")

    systems, entries = [], []
    for index, path in enumerate(files):
        system, system_entries = parse_system(path, index)
        systems.append(system)
        entries.extend(system_entries)

    version = (refs / "VERSION.txt").read_text(encoding="utf-8").strip().splitlines()
    data = {"version": version, "systems": systems, "entries": entries}
    OUT.write_text(
        "// Generated by tools/build_reference.py. Do not edit.\n"
        "window.REFERENCE = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    counts, tag_counts = {}, {}
    for entry in entries:
        counts[entry["k"]] = counts.get(entry["k"], 0) + 1
        for tag in entry.get("t", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    print(f"{len(systems)} systems, {len(entries)} entries -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    for kind, count in sorted(counts.items()):
        print(f"  {kind:10} {count}")
    print("Tags:", ", ".join(f"{t} {c}" for t, c in sorted(tag_counts.items(), key=lambda x: -x[1])))
    untagged = sum(1 for e in entries if not e.get("t"))
    print(f"Untagged entries: {untagged}")


if __name__ == "__main__":
    main()
