#!/usr/bin/env python3
"""
anime_sorter.py -- fold a messy, scattered anime collection into one shallow,
canonically-named library.

  * .mkv / .mp4 ONLY. Nothing else is ever touched.
  * NEVER deletes, NEVER overwrites. Every move -> a revertible manifest
    (same format MediaForge's Library Organiser uses).
  * Filename-first, then FOLDER-aware: files whose name has no real series
    title fall back to a folder-name consensus, then to a hand alias map,
    then to a strict AniList lookup; anything still unresolved is left
    exactly where it is and listed under NEEDS REVIEW.
  * Whole-collection de-duplication by quick content hash. Any file that
    collides with something already placed (same content, or a competing
    encode of the same episode) is MOVED to <library>/_DUPLICATES/<original
    path> for you to clear by hand -- never left scattered, never deleted.
  * An .mkv and an .mp4 of the same episode both land in the series folder
    ("Title - S01E05.mkv" + "Title - S01E05.mp4") -- linked but separate.
  * Target layout -- one folder per series, files directly inside:
        <library>/<Title (Year)>/<Title> - S01E05.mkv
        <library>/<Title (Year)>/<Title>.mkv            (movies)

Usage:
    anime_sorter.py --scan DIR [DIR ...] --library DIR              # dry run
    anime_sorter.py --scan DIR [DIR ...] --library DIR --apply      # execute
    anime_sorter.py --revert ~/MediaForgeData/manifests/XXXX.json   # undo
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anitopy  # noqa: E402
import requests  # noqa: E402

from mediaforge.config import MANIFEST_DIR, DATA_ROOT  # noqa: E402
from mediaforge.manifest import Manifest, quick_hash  # noqa: E402

VIDEO_EXTS = {".mkv", ".mp4"}
CACHE_PATH = DATA_ROOT / "anime_title_cache.json"

# whole folders (any depth) skipped entirely -- not anime
SKIP_DIR_NAMES = {
    "4k video downloader", "4k video downloader+", "$recycle.bin",
    "system volume information", ".trash-1000", "amv", "duplicate_vault",
    "ai_image_outputs", "effl",
}

# google-takeout / drive-export decoration on an otherwise real folder name
TAKEOUT_RE = re.compile(r"[-_ ]*\d{8}t\d{6}z[-_ ]*\d*[-_ ]*\d*\s*$", re.I)
SXXEXX_RE = re.compile(r"\bS(\d{1,2})[ _.]?E(\d{1,3})\b", re.I)
DUP_MARKER_RE = re.compile(r"\s*\(\d+\)(?=\.\w+$|$)|\s*\(\d+\)(?=this )", re.I)
EP_ONLY_RE = re.compile(r"(?:^|[ _\-.])(?:E|EP|Episode|Ep)[ _.]?(\d{1,3})(?:[ _.]|$)", re.I)
NUM_TAIL_RE = re.compile(r"(?:[ _]-[ _]|[ _])(\d{1,3})(?:v\d)?\s*$")
SEASON_TOKEN_RE = re.compile(r"\b(?:S|Season)[ _]?(\d{1,2})\b", re.I)
# "S01E01 - Some Prose Title" / "S01E01-Some Prose" -> the prose is an EPISODE title
EPTITLE_RE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)?S\d{1,2}[ _.]?E\d{1,3}\s*[-–—.:]\s*\S", re.I)

NOISE_RE = re.compile(
    r"""\[[^\]]*\]|\([^)]*\d{3,}p[^)]*\)|\((?:19|20)\d\d\)|
        \b(1080p|720p|480p|2160p|4k|bd|bluray|blu-ray|web-?dl|webrip|hdtv|
        hevc|x265|x264|h\.?26[45]|10bit|8bit|e-?opus|opus|aac|flac|
        dual-?audio|multi-?subs?|eng-?subs?|eng\s*sub|dual\s*audio|batch|
        uncensored|remux|disney|multi|dub)\b""",
    re.I | re.X,
)
NON_ANIME_RE = re.compile(
    r"(\b(AMV|MMV|MAD|lofi|future\s*bass|\d+\s*hour|mashup|BGM|RTX\s*\d|POV|8K|"
    r"gameplay|walkthrough|cyberpunk|seedance|kling|SVD|WhatsApp|DreamPunk)\b"
    r"|「AMV」|Minecraft\s*Animation"
    r"|\bEpisode\s*1\s*[-~]\s*12\b"          # "Episode 1 ~ 12" youtube compilation
    r"|\b1\s*[-~]\s*12\b.*\b(Anime|English\s*Dub\w*|Full\s*Screen)\b"
    r"|\bNew\s*Anime\s*20\d\d\b|\bFull\s*Screen\b"
    r"|Reincarnated as the (king|dark) )", re.I)

# ------------------------------------------------------------------ #
# folder shorthand -> canonical search term  (this collection's map) #
# keyed on the lowercased/spaced folder basename                     #
# ------------------------------------------------------------------ #
ALIAS = {
    # -- Bakup/Adrianne Lenker shorthand --
    "86 dub": "86 Eighty-Six",
    "ao haru ride": "Ao Haru Ride",
    "aparida": "Apparently Disillusioned Adventurers Will Save the World",
    "erased1": "Boku dake ga Inai Machi",
    "flowers and forests": "Kaoru Hana wa Rin to Saku",
    "happymarg": "Watashi no Shiawase na Kekkon",
    "jsdf": "GATE",
    "lis": "Kaguya-sama wa Kokurasetai",
    "lowtie": "Jaku-Chara Tomozaki-kun",
    "mmo rehab": "Net-juu no Susume",
    "nisekoi fakelove": "Nisekoi",
    "re life": "ReLIFE",
    "snafu": "Yahari Ore no Seishun Love Comedy wa Machigatteiru",
    "servamp": "Servamp",
    "tkgh": "Tokyo Ghoul",
    "re s1": "Tokyo Ghoul:re",
    "tokyo ghoul_re s2": "Tokyo Ghoul:re 2nd Season",
    "tokrav": "Tokyo Ravens",
    "there is someone i like": "Kono Kaisha ni Suki na Hito ga Imasu",
    "akame": "Akame ga Kill!",
    "crown": "Guilty Crown",
    "darwins game": "Darwin's Game",
    "demonschool": "Mairimashita! Iruma-kun",
    "demonsword": "Seiken Gakuin no Makentsukai",
    "devils line": "Devils' Line",
    "dressup": "Sono Bisque Doll wa Koi wo Suru",
    "expirenence": "KimiZero",
    "franxx": "Darling in the FranXX",
    "gamers": "Gamers!",
    "glassesgirl": "Suki na Ko ga Megane wo Wasureta",
    "hello": "Fuufu Ijou, Koibito Miman",
    "ice guy": "Koori Zokusei Danshi to Cool na Douryou Joshi",
    "irrig": "Mahouka Koukou no Rettousei",
    "irrimage2": "Mahouka Koukou no Rettousei S2",
    "iseleve": "I Got a Cheat Skill in Another World",
    "cheat skill": "I Got a Cheat Skill in Another World",
    "level2": "Lv2 kara Cheat datta Motoyuusha Kouho no Mattari Isekai Life",
    "levelon1": "Level 1 dakedo Unique Skill de Saikyou desu",
    "orange": "Orange",
    "over the moon": "Tonikaku Kawaii",
    "pet skurasou": "Sakurasou no Pet na Kanojo",
    "polar": "Seihantai na Kimi to Boku",
    "quint": "5-toubun no Hanayome",
    "realist": "Yumemiru Danshi wa Genjitsushugisha",
    "realstrong": "Jitsu wa Ore, Saikyou deshita?",
    "shiko": "Kawaii dake ja Nai Shikimori-san",
    "shikomori": "Kawaii dake ja Nai Shikimori-san",
    "survive": "Danjo no Yuujou wa Seiritsu Suru? (Iya, Shinai!!)",
    "torandora": "Toradora!",
    "trapped": "Otome Game Sekai wa Mob ni Kibishii Sekai desu",
    "treason": "Tensai Ouji no Akaji Kokka Saisei Jutsu",
    "verge of collapse": "Watari-kun no xx ga Houkai Sunzen",
    "wind guy": "Kaze no Stigma",
    "wiseguy": "Kenja no Mago",
    "sepender": "Owari no Seraph",
    "honeyleon": "Honey Lemon Soda",
    "another": "Another",
    "free": "Free!",
    # -- sorted/ shorthand --
    "angel": "The Angel Next Door Spoils Me Rotten",
    "actgirl": "Tomo-chan wa Onnanoko!",
    "bigguy": "Ore Monogatari!!",
    "cold": "Tsuredure Children",
    "coo": "A Couple of Cuckoos",
    "couple": "A Couple of Cuckoos",
    "couple2": "A Couple of Cuckoos S2",
    "dead": "Dead Account",
    "demon": "Oroka na Tenshi wa Akuma to Odoru",
    "has": "Kimi wa Houkago Insomnia",
    "hero": "Hero Without a Class",
    "invisi": "Kubo-san wa Mob wo Yurusanai",
    "kan": "Kanan-sama wa Akumade Choroi",
    "level": "Watashi ga Koibito ni Nareru Wake Naijan, Muri Muri! (Muri Janakatta!?)",
    "lildemon": "Tomodachi no Imouto ga Ore ni dake Uzai",
    "makeit": "Okiraku Ryoushu no Tanoshii Ryouchi Bouei",
    "moon": "Tsuki ga Kirei",
    "themoon": "Tsuki ga Kirei",
    "new": "Okiraku Ryoushu no Tanoshii Ryouchi Bouei",
    "new folder 2": "Dead Account",
    "oraku": "Otaku ni Yasashii Gal wa Inai",
    "ningen": "Ningen Fushin no Boukensha-tachi ga Sekai wo Sukuu you desu",
    "whitered": "Akagami no Shirayuki-hime",
    "3d": "3D Kanojo: Real Girl",
    "cute": "Class de 2-banme ni Kawaii Onnanoko to Tomodachi ni Natta",
}
# canonical title (+ first-broadcast year) for every series in THIS collection,
# keyed on norm_key() of whatever the resolver ends up searching (a filename
# title, an alias value, or a folder name). Checked BEFORE AniList so the sort
# is fast and deterministic and never needs the network for the known set.
SERIES = {
    "the angel next door spoils me rotten": ("The Angel Next Door Spoils Me Rotten", 2023),
    "otonari no tenshisama ni itsunomanika dame ningen ni sareteita ken":
        ("The Angel Next Door Spoils Me Rotten", 2023),
    "couple of cuckoos": ("A Couple of Cuckoos", 2022),
    "a couple of cuckoos": ("A Couple of Cuckoos", 2022),
    "a couple of cuckoos s2": ("A Couple of Cuckoos", 2022),
    "kakkou no iinazuke": ("A Couple of Cuckoos", 2022),
    "a sign of affection": ("A Sign of Affection", 2024),
    "86 eighty six": ("86 EIGHTY-SIX", 2021),
    "86 eightysix": ("86 EIGHTY-SIX", 2021),
    "akame ga kill": ("Akame ga Kill!", 2014),
    "another": ("Another", 2012),
    "ao no hako": ("Blue Box", 2024),
    "blue box": ("Blue Box", 2024),
    "engage kiss": ("Engage Kiss", 2022),
    "ningen fushin": ("Ningen Fushin: Adventurers Who Don't Believe in Humanity Will Save the World", 2023),
    "ningen fushin no boukenshatachi ga sekai wo sukuu you desu":
        ("Ningen Fushin: Adventurers Who Don't Believe in Humanity Will Save the World", 2023),
    "kids on the slope": ("Kids on the Slope", 2012),
    "kaoru hana wa rin to saku": ("The Fragrant Flower Blooms with Dignity", 2025),
    "grancrest senki": ("Record of Grancrest War", 2018),
    "watashi no shiawase na kekkon": ("My Happy Marriage", 2023),
    "gate": ("GATE", 2015),
    "kaguya sama love is war": ("Kaguya-sama: Love Is War", 2019),
    "kaguyasama love is war": ("Kaguya-sama: Love Is War", 2019),
    "kaguyasama wa kokurasetai": ("Kaguya-sama: Love Is War", 2019),
    "jakuchara tomozakikun": ("Bottom-tier Character Tomozaki", 2021),
    "recovery of an mmo junkie": ("Recovery of an MMO Junkie", 2017),
    "netjuu no susume": ("Recovery of an MMO Junkie", 2017),
    "amnesia": ("Amnesia", 2013),
    "a whisker away": ("A Whisker Away", 2020),
    "kimi no na wa": ("Your Name.", 2016),
    "your name": ("Your Name.", 2016),
    "honey lemon soda": ("Honey Lemon Soda", 2025),
    "free": ("Free!", 2013),
    "seraph of the end": ("Seraph of the End", 2015),
    "owari no seraph": ("Seraph of the End", 2015),
    "chivalry of a failed knight": ("Chivalry of a Failed Knight", 2015),
    "nisekoi": ("Nisekoi", 2014),
    "oshi no ko": ("Oshi no Ko", 2023),
    "relife": ("ReLIFE", 2016),
    "rezero": ("Re:ZERO -Starting Life in Another World-", 2016),
    "re zero": ("Re:ZERO -Starting Life in Another World-", 2016),
    "oregairu": ("My Teen Romantic Comedy SNAFU", 2013),
    "yahari ore no seishun love comedy wa machigatteiru": ("My Teen Romantic Comedy SNAFU", 2013),
    "servamp": ("Servamp", 2016),
    "tokyo ghoul": ("Tokyo Ghoul", 2014),
    "tokyo ghoulre": ("Tokyo Ghoul re", 2018),
    "tokyo ghoul re": ("Tokyo Ghoul re", 2018),
    "tokyo ravens": ("Tokyo Ravens", 2013),
    "horimiya": ("Horimiya", 2021),
    "komi cant communicate": ("Komi Can't Communicate", 2021),
    "komi can t communicate": ("Komi Can't Communicate", 2021),
    "i got a cheat skill in another world": ("I Got a Cheat Skill in Another World", 2023),
    "iseleve": ("I Got a Cheat Skill in Another World", 2023),
    "guilty crown": ("Guilty Crown", 2011),
    "the daily life of the immortal king": ("The Daily Life of the Immortal King", 2020),
    "darwins game": ("Darwin's Game", 2020),
    "darwin s game": ("Darwin's Game", 2020),
    "iruma kun": ("Welcome to Demon School! Iruma-kun", 2019),
    "irumakun": ("Welcome to Demon School! Iruma-kun", 2019),
    "mairimashita irumakun": ("Welcome to Demon School! Iruma-kun", 2019),
    "seiken gakuin no makentsukai": ("The Demon Sword Master of Excalibur Academy", 2023),
    "devils line": ("Devils' Line", 2018),
    "devil s line": ("Devils' Line", 2018),
    "my dress up darling": ("My Dress-Up Darling", 2022),
    "sono bisque doll wa koi wo suru": ("My Dress-Up Darling", 2022),
    "kimizero": ("Our Dating Story: The Experienced You and The Inexperienced Me", 2023),
    "darling in the franxx": ("DARLING in the FRANXX", 2018),
    "the quintessential quintuplets": ("The Quintessential Quintuplets", 2019),
    "5toubun no hanayome": ("The Quintessential Quintuplets", 2019),
    "gamers": ("Gamers!", 2017),
    "suki na ko ga megane wo wasureta": ("The Girl I Like Forgot Her Glasses", 2023),
    "fuufu ijou koibito miman": ("More Than a Married Couple, But Not Lovers", 2022),
    "koori zokusei danshi to cool na douryou joshi": ("The Ice Guy and His Cool Female Colleague", 2023),
    "the ice guy and his cool female colleague": ("The Ice Guy and His Cool Female Colleague", 2023),
    "mahouka koukou no rettousei": ("The Irregular at Magic High School", 2014),
    "mahouka": ("The Irregular at Magic High School", 2014),
    "the irregular at magic high school": ("The Irregular at Magic High School", 2014),
    "lv2 kara cheat datta motoyuusha kouho no mattari isekai life":
        ("Chillin' in Another World with Level 2 Super Cheat Powers", 2024),
    "level 1 dakedo unique skill de saikyou desu":
        ("My Unique Skill Makes Me OP even at Level 1", 2025),
    "orange": ("Orange", 2016),
    "tonikaku kawaii": ("TONIKAWA: Over the Moon for You", 2020),
    "tonikawa over the moon for you": ("TONIKAWA: Over the Moon for You", 2020),
    "sakurasou no pet na kanojo": ("The Pet Girl of Sakurasou", 2012),
    "sakura sou no pet na kanojo": ("The Pet Girl of Sakurasou", 2012),
    "seihantai na kimi to boku": ("You and I Are Polar Opposites", 2025),
    "yumemiru danshi wa genjitsushugisha": ("The Dreaming Boy Is a Realist", 2023),
    "jitsu wa ore saikyou deshita": ("I'm Actually the Strongest", 2023),
    "kawaii dake ja nai shikimorisan": ("Shikimori's Not Just a Cutie", 2022),
    "shikimori s not just a cutie": ("Shikimori's Not Just a Cutie", 2022),
    "danjo no yuujou wa seiritsu suru": ("Can a Boy-Girl Friendship Survive?", 2025),
    "toradora": ("Toradora!", 2008),
    "trapped in a dating sim": ("Trapped in a Dating Sim: The World of Otome Games Is Tough for Mobs", 2022),
    "otome game sekai wa mob ni kibishii sekai desu":
        ("Trapped in a Dating Sim: The World of Otome Games Is Tough for Mobs", 2022),
    "the genius prince s guide to raising a nation out of debt":
        ("The Genius Prince's Guide to Raising a Nation Out of Debt", 2022),
    "tensai ouji no akaji kokka saisei jutsu":
        ("The Genius Prince's Guide to Raising a Nation Out of Debt", 2022),
    "watarikun no xx ga houkai sunzen": ("Watari-kun's ****** Is About to Collapse", 2017),
    "kaze no stigma": ("Kaze no Stigma", 2007),
    "kenja no mago": ("Wise Man's Grandchild", 2019),
    "tomochan wa onnanoko": ("Tomo-chan Is a Girl!", 2023),
    "ore monogatari": ("My Love Story!!", 2015),
    "tsuredure children": ("Tsuredure Children", 2017),
    "kimi wa houkago insomnia": ("Insomniacs After School", 2023),
    "hero without a class": ("Hero Without a Class: Who Even Needs Skills?!", 2024),
    "kubosan wa mob wo yurusanai": ("Kubo Won't Let Me Be Invisible", 2023),
    "kanansama wa akumade choroi": ("Mistress Kanan is Devilishly Easy", 2026),
    "kanan sama wa akumade choroi": ("Mistress Kanan is Devilishly Easy", 2026),
    "watashi ga koibito ni nareru wake naijan muri muri muri janakatta":
        ("There's No Freaking Way I'll Be Your Lover! Unless…", 2024),
    "watashi ga koibito ni nareru wake naijan muri muri":
        ("There's No Freaking Way I'll Be Your Lover! Unless…", 2024),
    "yamadakun to lv999 no koi wo suru":
        ("There's No Freaking Way I'll Be Your Lover! Unless…", 2024),
    "yamada kun to lv999 no koi wo suru":
        ("There's No Freaking Way I'll Be Your Lover! Unless…", 2024),
    "hero without a class who even needs skills":
        ("Hero Without a Class: Who Even Needs Skills?!", 2024),
    "tomodachi no imouto ga ore ni dake uzai": ("My Friend's Little Sister Has It In for Me!", 2025),
    "okiraku ryoushu no tanoshii ryouchi bouei":
        ("Easygoing Territory Defense by the Optimistic Lord", 2025),
    "tsuki ga kirei": ("Tsukigakirei", 2017),
    "otaku ni yasashii gal wa inai": ("Gals Can't Be Kind to Otaku!?", 2026),
    "akagami no shirayukihime": ("Snow White with the Red Hair", 2015),
    "snow white with the red hair": ("Snow White with the Red Hair", 2015),
    "3d kanojo real girl": ("3D Kanojo: Real Girl", 2018),
    "class de 2banme ni kawaii onnanoko to tomodachi ni natta":
        ("I Became Friends with the Second Cutest Girl in Class", 2025),
    "oroka na tenshi wa akuma to odoru": ("The Foolish Angel Dances with the Devil", 2025),
    "hotarubi no mori e": ("Into the Forest of Fireflies' Light", 2011),
    "sankarea": ("Sankarea: Undying Love", 2012),
    "skip and loafer": ("Skip and Loafer", 2023),
    "solo leveling": ("Solo Leveling", 2024),
    "charlotte": ("Charlotte", 2015),
    "erased": ("Erased", 2016),
    "boku dake ga inai machi": ("Erased", 2016),
    "ao haru ride": ("Blue Spring Ride", 2014),
    "blue spring ride": ("Blue Spring Ride", 2014),
    "fugukan": ("Even Given the Worthless “Appraiser” Class, I'm Actually the Strongest", 2025),
    "koe no katachi": ("A Silent Voice", 2016),
    "a silent voice": ("A Silent Voice", 2016),
    "josee the tiger and the fish": ("Josee, the Tiger and the Fish", 2020),
    "howl s moving castle": ("Howl's Moving Castle", 2004),
    "howls moving castle": ("Howl's Moving Castle", 2004),
    "i want to eat your pancreas": ("I Want to Eat Your Pancreas", 2018),
    "kimi no suizou wo tabetai": ("I Want to Eat Your Pancreas", 2018),
    "fruits basket": ("Fruits Basket (2019)", 2019),
    "senpai ga uzai kouhai no hanashi": ("My Senpai Is Annoying", 2021),
    "kono kaisha ni suki na hito ga imasu": ("I Have a Crush at Work", 2025),
    "dead account": ("Dead Account", 2026),
    "omagoto": ("ROLL OVER AND DIE", 2026),
    "omae gotoki": ("ROLL OVER AND DIE", 2026),
    "aparida": ("I Left My A-Rank Party to Help My Former Students Reach the Dungeon Depths!", 2025),
}

# folder basename -> forced season number
SEASON_HINT = {
    "oregairu 3": 3, "irrimage2": 2, "irrig": 1, "tokyo ghoul_re s2": 2,
    "re s1": 1, "couple2": 2,
}
# episode-title folders where a distinctive word in the episode titles names the show
EPTITLE_KEYWORD = {
    "senpai": "Senpai ga Uzai Kouhai no Hanashi",
}
# folders we know we cannot resolve -> straight to review (no bad guesses)
FORCE_REVIEW = {"prideswordthing"}


def clean_component(s: str) -> str:
    s = re.sub(r"[:/]+", " ", s or "")
    s = re.sub(r'[<>"\\|?*\x00-\x1f]', "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def strip_noise(s: str) -> str:
    s = NOISE_RE.sub(" ", s or "")
    s = re.sub(r"[._]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -_")


def norm_key(s: str) -> str:
    s = strip_noise((s or "").lower())
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def akey(s: str) -> str:
    """Light key for the curated ALIAS / SERIES dicts: lowercase, drop intra-word
    punctuation ('Tomo-chan' -> 'tomochan'), other separators -> space, collapse.
    Unlike norm_key it does NOT drop words like 'dub'."""
    s = (s or "").lower().replace("_", "-")
    s = re.sub(r"(?<=\w)['’\-](?=\w)", "", s)      # tomo-chan -> tomochan
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def akeys(s: str):
    """Both key forms: hyphen-joined ('kaguyasama') and hyphen-spaced
    ('kaguya sama'). Curated dicts are indexed under both."""
    j = akey(s)
    sp = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()
    return {j, sp} if sp != j else {j}


def folder_name_clean(name: str) -> str:
    n = TAKEOUT_RE.sub("", name)
    n = re.sub(r"\bS0?1\b\s*$", "", n).strip(" -_")
    return strip_noise(n)


CRYPTIC_STOP = {
    "new", "old", "has", "keep", "temp", "tmp", "misc", "sorted", "aniemieie",
    "bakup", "z", "import", "video", "videos", "anime", "d", "dd", "stuff",
}


def is_cryptic_folder(name: str) -> bool:
    n = norm_key(name)
    if not n or n in CRYPTIC_STOP:
        return True
    if re.fullmatch(r"[a-z]{1,3}", n):
        return True
    if re.fullmatch(r"\d+", n):
        return True
    if re.match(r"new folder", n) or re.match(r"drive download", n):
        return True
    words = n.split()
    # single short lowercase token that isn't an obvious real word/title
    if len(words) == 1 and len(n) <= 7:
        return True
    return False


# re-key the curated dicts under both key forms so lookups survive punctuation
def _reindex(d):
    out = {}
    for k, v in d.items():
        for kk in akeys(k):
            out.setdefault(kk, v)
    return out


ALIAS = _reindex(ALIAS)
SERIES = _reindex(SERIES)
EPTITLE_KEYWORD = _reindex(EPTITLE_KEYWORD)
SEASON_HINT = _reindex(SEASON_HINT)
FORCE_REVIEW = {kk for k in FORCE_REVIEW for kk in akeys(k)}


# ------------------------------------------------------------------ #
class TitleResolver:
    QUERY = """
    query ($search: String) {
      Page(perPage: 8) {
        media(search: $search, type: ANIME) {
          id format episodes seasonYear popularity
          startDate { year }
          title { romaji english }
          synonyms
        }
      }
    }"""

    def __init__(self, offline=False):
        self.offline = offline
        self._last = 0.0
        self.cache = {}
        if CACHE_PATH.exists():
            try:
                self.cache = json.loads(CACHE_PATH.read_text("utf-8"))
            except Exception:
                self.cache = {}
        self._dirty = 0

    def save(self):
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), "utf-8")
        self._dirty = 0

    def _fetch(self, term):
        if self._last:
            time.sleep(max(0, 0.9 - (time.time() - self._last)))
        for attempt in range(3):
            try:
                r = requests.post("https://graphql.anilist.co",
                                  json={"query": self.QUERY, "variables": {"search": term}},
                                  timeout=20)
                self._last = time.time()
                if r.status_code == 429:
                    time.sleep(5 + 5 * attempt)
                    continue
                return (((r.json() or {}).get("data") or {}).get("Page") or {}).get("media") or []
            except Exception:
                time.sleep(2)
        return []

    @staticmethod
    def _match(term, m):
        """0..1 similarity of `term` to this media's best name (no popularity)."""
        cand = norm_key(term)
        cw = set(cand.split())
        best = 0.0
        for nm in [m["title"].get("romaji"), m["title"].get("english")] + (m.get("synonyms") or []):
            k = norm_key(nm or "")
            if not k:
                continue
            kw = set(k.split())
            if k == cand:
                return 1.0
            if cand and (cand in k or k in cand):
                best = max(best, 0.9)
            if cw and kw:
                j = len(cw & kw) / len(cw | kw)
                # also credit "candidate is a prefix subset of the name"
                sub = len(cw & kw) / len(cw) if cw else 0
                best = max(best, j, sub * 0.85)
        return best

    def resolve(self, term, want_series=True):
        term = strip_noise(term)
        if len(term) < 2:
            return None
        ck = ("s" if want_series else "m") + "|" + norm_key(term)
        if ck in self.cache:
            return self.cache[ck] or None
        if self.offline:
            return None
        media = self._fetch(term)
        scored = []
        for m in media:
            s = self._match(term, m)
            # gentle tie-break by popularity only once past the bar
            s2 = s + min(m.get("popularity") or 0, 300000) / 6_000_000
            scored.append((s, s2, m))
        scored.sort(key=lambda t: t[1], reverse=True)
        result = None
        if scored and scored[0][0] >= 0.55:
            m = scored[0][2]
            title = (m["title"].get("english") or m["title"].get("romaji") or term).strip()
            year = m.get("seasonYear") or (m.get("startDate") or {}).get("year")
            result = {"title": title, "year": year, "format": m.get("format"),
                      "episodes": m.get("episodes"), "score": round(scored[0][0], 2)}
        self.cache[ck] = result or {}
        self._dirty += 1
        if self._dirty >= 15:
            self.save()
        return result


# ------------------------------------------------------------------ #
def parse_file(path: Path, scan_root: Path):
    raw = path.stem
    name = DUP_MARKER_RE.sub("", raw)
    is_eptitle = bool(EPTITLE_RE.match(raw))

    season = episode = None
    m = SXXEXX_RE.search(name)
    if m:
        season, episode = int(m.group(1)), int(m.group(2))

    ana = {}
    try:
        ana = anitopy.parse(name + path.suffix) or {}   # cleaned of "(1)" markers
    except Exception:
        pass
    if episode is None and ana.get("episode_number"):
        en = ana["episode_number"]
        alt = ana.get("episode_number_alt")
        # "Title - 20(1)" -> anitopy reads ep 1 + alt 20; the real episode is 20
        if alt and str(alt).isdigit() and str(en).isdigit() and int(alt) > int(en):
            en = alt
        en = en[0] if isinstance(en, list) else en
        try:
            episode = int(str(en))
        except ValueError:
            episode = None
    if episode is None:
        m = (EP_ONLY_RE.search(name) or NUM_TAIL_RE.search(name)
             or re.search(r"[ _]-\s?(\d{1,3})\s?-(?:\s|\[|$)", name)   # "Title -01-[BD]"
             or re.match(r"\s*(\d{1,3})\s*[-.– ]", name))               # "08 - Fragile"
        if m and not re.fullmatch(r"(19|20)\d\d", m.group(1)):
            episode = int(m.group(1))
    if season is None and ana.get("anime_season"):
        s = ana["anime_season"]
        s = s[0] if isinstance(s, list) else s
        try:
            season = int(s)
        except (ValueError, TypeError):
            season = None

    ftitle = None
    if not is_eptitle:
        t = strip_noise(ana.get("anime_title") or "")
        t = SXXEXX_RE.sub("", t).strip(" -_")
        mt = re.search(r"\bS(\d)\b\s*$", t)               # trailing "S2"
        if mt and season is None:
            season = int(mt.group(1))
        t = re.sub(r"\bS\d\b\s*$", "", t).strip(" -_")
        t = re.sub(r"[ _-]+\d{1,3}\s*$", "", t).strip(" -_")   # trailing "- 01" / "-01"
        # also "... Season 03" / "... Anime Part 2" style tails from the raw name
        ms = re.search(r"\b(?:season|part)\s*0?(\d)\b", raw, re.I)
        if ms and season is None:
            season = int(ms.group(1))
        if t and len(t) >= 4 and not re.match(r"^(ep?\d+|\d+|episode\b)", t, re.I) \
                and not EPTITLE_RE.match(t + " x"):
            ftitle = t

    rel = path.relative_to(scan_root)
    folders = []
    for part in list(rel.parts[:-1])[::-1]:
        sm = SEASON_TOKEN_RE.fullmatch(part.strip()) or re.fullmatch(r"season\s*\d+", part.strip(), re.I)
        if sm:
            n = re.search(r"\d+", part)
            if n and season is None:
                season = int(n.group())
            continue
        for kk in akeys(part):
            if kk in SEASON_HINT and season is None:
                season = SEASON_HINT[kk]
        folders.append(part)

    return {"path": path, "raw": raw, "season": season, "episode": episode,
            "ftitle": ftitle, "is_eptitle": is_eptitle, "folders": folders}


def _is_movie(r, info):
    if info["episode"] is not None:
        return False
    return (r and r.get("format") in {"MOVIE", "SPECIAL"}) or (r and r.get("episodes") == 1)


def _series_table(cand):
    """Look cand up in the hand-verified SERIES table, trying a few variants."""
    variants = []
    for k in akeys(cand):
        variants += [k,
                     re.sub(r"\s+s\d+\s*$", "", k),
                     re.sub(r"\s+season\s*\d+\s*$", "", k),
                     re.sub(r"\s+\d+\s*$", "", k),
                     re.sub(r"\s+(anime|tv|the animation|movie|the movie|dub|dubbed)\s*$", "", k)]
    for kk in variants:
        if kk in SERIES:
            return SERIES[kk]
    # a curated key is a clear prefix of the candidate (e.g. filename carried a
    # subtitle the table key omits) -- only for keys long enough to be specific
    for kk in variants:
        for sk, val in SERIES.items():
            if len(sk) >= 12 and (kk.startswith(sk + " ") or sk.startswith(kk + " ")):
                return val
    return None


def resolve_all(parsed, resolver: TitleResolver, log=print):
    """parsed: list of file-info dicts. Returns {id(info): (title, year, is_movie, how)}."""
    byfolder = defaultdict(list)
    for info in parsed:
        byfolder[info["path"].parent].append(info)

    out = {}
    for folder, infos in byfolder.items():
        ftitles = Counter(norm_key(i["ftitle"]) for i in infos if i["ftitle"])
        consensus = None
        if ftitles:
            top, n = ftitles.most_common(1)[0]
            if n >= max(2, 0.5 * sum(ftitles.values())):
                consensus = next(i["ftitle"] for i in infos
                                 if i["ftitle"] and norm_key(i["ftitle"]) == top)
        titles_blob = " ".join(i["raw"].lower() for i in infos)
        force_review = norm_key(folder.name) in FORCE_REVIEW

        for info in infos:
            if force_review:
                out[id(info)] = (None, None, False, "force-review")
                continue

            # ordered candidate strings, best signal first
            cands = []
            if info["ftitle"]:
                cands.append(("file", info["ftitle"]))
            if consensus and (not info["ftitle"] or norm_key(consensus) != norm_key(info["ftitle"])):
                cands.append(("folder-consensus", consensus))
            if info["is_eptitle"]:
                for kw, show in EPTITLE_KEYWORD.items():
                    if titles_blob.count(kw) >= 3:
                        cands.append(("eptitle-keyword", show))
                        break
            for fol in info["folders"]:
                ali = None
                for cform in (fol, folder_name_clean(fol), TAKEOUT_RE.sub("", fol)):
                    for kk in akeys(cform):
                        if kk in ALIAS:
                            ali = ALIAS[kk]
                            break
                    if ali:
                        break
                if ali:
                    cands.append((f"alias:{fol}", ali))
                fc = folder_name_clean(fol) or akey(TAKEOUT_RE.sub("", fol))
                if fc and not is_cryptic_folder(fol) and len(fc) >= 5:
                    cands.append((f"folder:{fol}", fc))

            resolved = None
            for how, cand in cands:
                hit = _series_table(cand)
                if hit:
                    resolved = (hit[0], hit[1], info["episode"] is None, f"{how}->table")
                    break
            if resolved is None:
                for how, cand in cands:
                    r = resolver.resolve(cand)
                    if r:
                        resolved = (r["title"], r.get("year"), _is_movie(r, info),
                                    f"{how}->anilist({r['score']})")
                        break
            if resolved is None:
                # last resort: trust an alias's own text, or a long filename title
                for how, cand in cands:
                    if how.startswith("alias"):
                        resolved = (clean_component(cand), None, info["episode"] is None,
                                    how + "->raw")
                        break
                    if how == "file" and len(cand) >= 9 and " " in cand:
                        resolved = (clean_component(cand), None, info["episode"] is None,
                                    "file->raw")
                        break
            out[id(info)] = resolved or (None, None, False, "unidentified")
    resolver.save()
    return out


# ------------------------------------------------------------------ #
def build_plan(scan_roots, library: Path, resolver: TitleResolver, log=print):
    files = []
    for root in scan_roots:
        root = Path(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.strip().lower() not in SKIP_DIR_NAMES]
            for fn in filenames:
                if Path(fn).suffix.lower() in VIDEO_EXTS:
                    files.append((root, Path(dirpath) / fn))
    log(f"  {len(files)} .mkv/.mp4 files found")

    parsed = [parse_file(p, root) for root, p in files]
    log("  resolving titles (AniList, cached)…")
    res = resolve_all(parsed, resolver, log)

    # deterministic: .mkv before .mp4, then shallower/shorter source path first
    parsed.sort(key=lambda i: (i["path"].suffix.lower() != ".mkv",
                               len(str(i["path"])), str(i["path"])))

    plan = []
    seen_hash = {}
    claimed = {}
    series_years = {}

    for info in parsed:
        p = info["path"]
        try:
            size = p.stat().st_size
        except OSError:
            continue
        row = {"src": str(p), "size": size, "action": None, "dst": None,
               "series": None, "note": ""}

        if NON_ANIME_RE.search(info["raw"]):
            row.update(action="skip", note="not an anime episode (left in place)")
            plan.append(row); continue

        title, year, is_movie, how = res.get(id(info), (None, None, False, "?"))
        if not title:
            row.update(action="review", note=f"{how}: {info['raw'][:70]}")
            plan.append(row); continue

        if year:
            series_years.setdefault(title, year)
        year = series_years.get(title)
        row["series"] = title

        season = info["season"] or 1
        episode = info["episode"]
        folder = clean_component(f"{title} ({year})" if year else title)
        ext = p.suffix.lower()
        if is_movie or episode is None:
            base = clean_component(title)
        else:
            base = f"{clean_component(title)} - S{season:02d}E{episode:02d}"
        dst = library / folder / f"{base}{ext}"
        qh = quick_hash(p)

        if str(dst) == str(p):
            row.update(action="ok", dst=str(dst), note=f"already sorted [{how}]")
            plan.append(row); continue

        collide = (str(dst).lower() in claimed) or \
                  (dst.exists() and str(dst) != str(p))
        if collide:
            existing_qh = claimed.get(str(dst).lower()) or (quick_hash(dst) if dst.exists() else None)
            kind = "identical" if (qh and qh == existing_qh) else "competing encode"
            rel = Path(*p.parts[-4:])
            for sr in scan_roots:
                sr = Path(sr)
                if sr == p.parent or sr in p.parents:
                    rel = p.relative_to(sr.parent)
                    break
            dpath = library / "_DUPLICATES" / rel
            b = 2
            while dpath.exists() or str(dpath).lower() in claimed:
                dpath = dpath.with_stem(f"{dpath.stem} ({b})"); b += 1
            row.update(action="dupe", dst=str(dpath),
                       note=f"{kind} of {Path(dst).name} — parked for your review")
            claimed[str(dpath).lower()] = qh
            plan.append(row); continue

        if dst.exists() and qh and quick_hash(dst) == qh:
            row.update(action="skip", dst=str(dst), note="already in library (identical)")
            plan.append(row); continue

        row.update(action="move", dst=str(dst), note=how)
        claimed[str(dst).lower()] = qh
        if qh:
            seen_hash.setdefault(qh, str(dst))
        plan.append(row)

    resolver.save()
    return plan


# ------------------------------------------------------------------ #
def write_report(plan, path):
    c = Counter(r["action"] for r in plan)
    by_series = Counter(r["series"] for r in plan if r["action"] == "move")
    L = ["ANIME SORT PLAN", "=" * 72]
    for k in ("move", "dupe", "ok", "skip", "review"):
        L.append(f"  {k:8s} {c.get(k, 0)}")
    L.append(f"  series   {len(by_series)}")
    L.append("\nSERIES (episodes moved in):")
    for s, n in sorted(by_series.items()):
        L.append(f"  {n:3d}  {s}")
    L.append("\nNEEDS REVIEW (left untouched):")
    for r in plan:
        if r["action"] == "review":
            L.append(f"  {r['note']}\n        {r['src']}")
    L.append("\nPARKED IN _DUPLICATES (yours to clear):")
    for r in plan:
        if r["action"] == "dupe":
            L.append(f"  {r['src']}\n    -> {r['dst']}   [{r['note']}]")
    L.append("\nSKIPPED (non-anime / already there):")
    for r in plan:
        if r["action"] == "skip":
            L.append(f"  {r['src']}  ({r['note']})")
    L.append("\nFULL MOVE LIST:")
    for r in plan:
        if r["action"] == "move":
            L.append(f"  {r['src']}\n    -> {r['dst']}   [{r['note']}]")
    Path(path).write_text("\n".join(L), "utf-8")
    return c, by_series


def apply_plan(plan, log=print):
    import shutil
    man = Manifest(label="anime-sort")
    done = failed = 0
    for r in plan:
        if r["action"] not in ("move", "dupe"):
            continue
        src, dst = Path(r["src"]), Path(r["dst"])
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            log(f"  ! exists, skip: {dst}")
            continue
        try:
            if src.stat().st_dev == dst.parent.stat().st_dev:
                os.rename(src, dst); op = "move"
            else:
                shutil.copy2(src, dst); op = "copy"   # never unlink the source
            man.record(op, src, dst, size=r["size"], note=r["note"])
            done += 1
            if done % 100 == 0:
                log(f"  … {done}")
        except Exception as e:
            failed += 1
            log(f"  ! {e}: {src}")
    mp = man.save()
    log(f"\n  {done} placed, {failed} failed.\n  manifest: {mp}")
    log(f"  revert:  python tools/anime_sorter.py --revert {mp}")
    return mp


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", nargs="+")
    ap.add_argument("--library")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--report", default=str(MANIFEST_DIR / "anime_sort_plan.txt"))
    args = ap.parse_args()

    if args.revert:
        from mediaforge.manifest import revert
        u, s, np_ = revert(args.revert, log=print)
        print(f"reverted {u}, skipped {s}\nnew manifest: {np_}")
        return
    if not args.scan or not args.library:
        ap.error("need --scan and --library (or --revert)")

    library = Path(args.library).expanduser().resolve()
    library.mkdir(parents=True, exist_ok=True)
    resolver = TitleResolver(offline=args.offline)
    print(f"scanning {len(args.scan)} roots -> {library}")
    plan = build_plan([Path(s).expanduser().resolve() for s in args.scan], library, resolver)
    c, by = write_report(plan, args.report)
    print("\n" + "=" * 56)
    for k in ("move", "dupe", "ok", "skip", "review"):
        print(f"  {k:8s} {c.get(k, 0)}")
    print(f"  series   {len(by)}\n  plan -> {args.report}")
    if args.apply:
        print("\napplying…")
        apply_plan(plan)
    else:
        print("\ndry run — re-run with --apply")


if __name__ == "__main__":
    main()
