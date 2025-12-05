import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, date
import re
from typing import List, Dict, Optional

st.set_page_config(page_title="Kosárlabda meccs és statisztika (Flashscore)", layout="wide")
st.title("🏀 Kosárlabda meccs kereső és statisztika (Flashscore alapú, JSON+HTML fallback)")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}

# -----------------------
# Helper: lekéri a napi JSON feedet (Flashscore rejtett feed)
# -----------------------
def fetch_daily_json_feed(day: date) -> Optional[Dict]:
    """Próbálja betölteni a Flashscore napi JSON feedjét.
    URL pattern (feltételezett): https://d.flashscore.com/x/feed/f_1_{YYYYMMDD}_en_1
    Ez nem hivatalos dokumentált API — ha nem elérhető, None-t ad vissza.
    """
    ymd = day.strftime("%Y%m%d")
    url = f"https://d.flashscore.com/x/feed/f_1_{ymd}_en_1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# -----------------------
# Helper: kinyerjük a meccseket a JSON-ból, ha a struktúra ismert
# -----------------------
def parse_matches_from_daily_json(data: Dict) -> List[Dict]:
    """Best-effort: megpróbáljuk kinyerni a meccsek listáját a napi JSON feedből.
    Visszatérési lista: dict-ek {match_id, home, away, home_score, away_score, raw}
    """
    matches = []
    # Lehetséges helyek ahol az események lehetnek: 'ev', 'events', 'eventsData', 'sports'
    # Próbálunk néhány feltehető kulcsot
    candidates = []
    for k in ["ev", "events", "eventsData", "events_by_tournament", "sport_events", "data"]:
        v = data.get(k)
        if isinstance(v, list):
            candidates = v
            break

    # Ha találtunk listát, próbáljuk feldolgozni
    if not candidates:
        # Ha nincs, keresünk minden listában, ami dict-eket tartalmaz
        for val in data.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                candidates = val
                break

    for item in candidates:
        try:
            # Többféle struktúra lehetséges, igyekszünk rugalmasan kezelni
            # gyakori mezők: 'id' vagy 'sid' vagy 'id2', csapatok: 'home', 'away' vagy 'homeName'/'awayName'
            mid = item.get("id") or item.get("matchId") or item.get("sid") or item.get("intId")
            # Néhány feedben a csapatok egy 'competitors' listában vannak
            home = item.get("homeTeam", {}).get("name") if isinstance(item.get("homeTeam"), dict) else item.get("home")
            away = item.get("awayTeam", {}).get("name") if isinstance(item.get("awayTeam"), dict) else item.get("away")
            # alternatív: competitors
            if not home or not away:
                comps = item.get("competitors") or item.get("participants") or item.get("teams")
                if isinstance(comps, list) and len(comps) >= 2:
                    # találjuk a home/away mezőket ha vannak
                    try:
                        home = comps[0].get("name") or comps[0].get("team") or comps[0].get("home")
                        away = comps[1].get("name") or comps[1].get("team") or comps[1].get("away")
                    except Exception:
                        pass
            # pontszámok
            home_score = None
            away_score = None
            # gyakori hely: 'score' vagy 'homeScore'/'awayScore'
            if "homeScore" in item or "awayScore" in item:
                home_score = item.get("homeScore")
                away_score = item.get("awayScore")
            else:
                score = item.get("score") or item.get("result")
                if isinstance(score, dict):
                    home_score = score.get("home")
                    away_score = score.get("away")
            # Ha van slug/link mező, megpróbáljuk kinyerni a flashscore ID-t
            link = item.get("slug") or item.get("link") or item.get("url")
            # normalize
            if isinstance(link, str) and "/match/" in link:
                # pl. /match/7uYgXEqb/
                m = re.search(r"/match/([^/]+)", link)
                if m:
                    mid = m.group(1)
            if home and away:
                matches.append({
                    "match_id": str(mid) if mid is not None else None,
                    "home": home,
                    "away": away,
                    "home_score": home_score,
                    "away_score": away_score,
                    "raw": item
                })
        except Exception:
            continue
    return matches


# -----------------------
# Helper: napi HTML lista (fallback a JSON helyett)
# -----------------------
def fetch_daily_html_matches(day: date) -> List[Dict]:
    """Ha a JSON feed nem működik, lekérdezzük a flashscore napi oldalt és kigyűjtjük a meccseket."""
    ymd = day.strftime("%Y-%m-%d")
    url = f"https://www.flashscore.com/basketball/?d={ymd}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")

        matches = []
        # Keresünk minden <a> elemet, ahol href tartalmaz '/match/'
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/match/" not in href:
                continue
            # A környező szövegből próbáljuk kinyerni a csapatneveket
            text = a.get_text(separator=" ", strip=True)
            # tipikusan "Home - Away" vagy "Home Away" lehet benne; használjunk regexet
            # keressünk nagybetűs szócsoportokat szeparátorként '-'
            if "-" in text:
                parts = [p.strip() for p in text.split("-") if p.strip()]
                if len(parts) >= 2:
                    home = parts[0]
                    away = parts[1]
                else:
                    continue
            else:
                # ha nincs '-', próbáljuk parent node-ot
                parent = a.parent
                txt = parent.get_text(separator=" ", strip=True)
                m = re.search(r"(.+?)\s+[-–]\s+(.+)", txt)
                if m:
                    home = m.group(1).strip()
                    away = m.group(2).strip()
                else:
                    continue

            # match_id kinyerése href-ből: /match/7uYgXEqb/
            m2 = re.search(r"/match/([^/]+)", href)
            match_id = m2.group(1) if m2 else None

            # megpróbáljuk a pontszámot is kinyerni a sibling elemekből
            score = "?"
            try:
                # keresünk score osztályokat a környezetben
                container = a.find_parent()
                if container:
                    sc = container.find(string=re.compile(r"\d+\s*:\s*\d+|\d+\s*-\s*\d+"))
                    if sc:
                        score = sc.strip()
            except Exception:
                score = "?"

            matches.append({
                "match_id": match_id,
                "home": home,
                "away": away,
                "home_score": None,
                "away_score": None,
                "score_text": score
            })
        # deduplikálás: azonos home-away párosokra csak az első
        uniq = []
        seen = set()
        for m in matches:
            key = (m.get("home","").lower(), m.get("away","").lower())
            if key in seen:
                continue
            seen.add(key)
            uniq.append(m)
        return uniq
    except Exception:
        return []


# -----------------------
# Keresés: a felhasználó által beírt részleges név alapján szűrünk
# -----------------------
def filter_matches_by_team(matches: List[Dict], team_query: str) -> List[Dict]:
    q = team_query.strip().lower()
    found = []
    for m in matches:
        home = (m.get("home") or "").lower()
        away = (m.get("away") or "").lower()
        if q in home or q in away:
            found.append(m)
    return found


# -----------------------
# Részletes meccs JSON feed lekérése (match részletek)
# -----------------------
def fetch_match_json_detail(match_id: str) -> Optional[Dict]:
    """Próbálja a Flashscore részletes JSON feedet betölteni.
    Feltételezett pattern: https://d.flashscore.com/x/feed/d_1_{MATCH_ID}_en_1
    """
    if not match_id:
        return None
    url = f"https://d.flashscore.com/x/feed/d_1_{match_id}_en_1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# -----------------------
# JSON részletes adatból stat kinyerése (best-effort)
# -----------------------
def parse_player_stats_from_match_json(data: Dict) -> Optional[pd.DataFrame]:
    """Best-effort kinyerés a részletes match JSON-ból.
    Visszatér DataFrame-el, aminek magyar+angol címei lesznek.
    """
    try:
        # Keresünk kulcsokat, ahol előfordulhatnak player statok: 'playerStatistics', 'players', 'statistics'
        plist = None
        # keresés a dict-ben: minden value, ami lista és elemei dict-ek, és van 'player' kulcs
        def find_player_lists(obj):
            found = []
            if isinstance(obj, dict):
                for v in obj.values():
                    found += find_player_lists(v)
            elif isinstance(obj, list):
                if obj and isinstance(obj[0], dict) and "player" in obj[0]:
                    found.append(obj)
                else:
                    for it in obj:
                        found += find_player_lists(it)
            return found

        found_lists = find_player_lists(data)
        if found_lists:
            # elsőt feldolgozzuk
            plist = found_lists[0]
        else:
            # alternatív: keresünk 'teamStatistics' -> 'players'
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, dict) and "players" in v:
                        plist = v.get("players")
                        break

        if not plist:
            return None

        rows = []
        for p in plist:
            try:
                player = p.get("player", {})
                name = player.get("name") or player.get("fullName") or player.get("displayName")
                team = p.get("team", {}).get("name") or p.get("teamName") or p.get("team")
                # mezők: points, assists, rebounds, minutes stb.
                pts = p.get("points") if "points" in p else p.get("pts") or p.get("scored")
                ast = p.get("assists") if "assists" in p else p.get("ast")
                reb = p.get("rebounds") if "rebounds" in p else p.get("reb")
                # Ha nincsenek explicit mezők, nézzük statlist-et
                if pts is None and p.get("statistics"):
                    for stat in p.get("statistics"):
                        k = stat.get("name","").lower()
                        if "points" in k or "pts" in k:
                            pts = stat.get("value")
                        if "assist" in k:
                            ast = stat.get("value")
                        if "reb" in k:
                            reb = stat.get("value")
                rows.append({
                    "Csapat (Team)": team or "?",
                    "Játékos (Player)": name or "?",
                    "Pont (Points)": pts if pts is not None else "?",
                    "Assziszt (Assists)": ast if ast is not None else "?",
                    "Lepattanó (Rebounds)": reb if reb is not None else "?"
                })
            except Exception:
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)
        return df
    except Exception:
        return None


# -----------------------
# HTML scraping a meccs oldalról (fallback)
# -----------------------
def fetch_match_stats_by_html(match_id: str) -> Optional[pd.DataFrame]:
    """Best-effort: lekéri a flashscore match oldalát és kigyűjti a player stat táblákat."""
    if not match_id:
        return None
    url = f"https://www.flashscore.com/match/{match_id}/#/match-summary"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")

        # Flashscore oldalakon a stat táblák lehetnek <table> elemek, keressük a "PTS", "AST", "REB" fejléceket.
        tables = soup.find_all("table")
        candidate = None
        for table in tables:
            headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]
            # ha van PTS vagy POINTS a headerek között --> valószínű stat tábla
            if any(h in ("PTS", "POINTS", "P") for h in headers):
                candidate = table
                break

        if candidate is None:
            # esetleg keresünk div-ekben stat sorokat
            # fallback: nézzünk meg minden szöveget, és próbáljunk név + szám párokat kigyűjteni
            text = soup.get_text(" ", strip=True)
            # ez nagyon kevésbé megbízható, ezért csak később használjuk
            return None

        # olvassuk be a táblát pandas-szal (ha jól van strukturálva)
        try:
            df_html = pd.read_html(str(candidate))
            if not df_html:
                return None
            df0 = df_html[0]
            # Megpróbálunk közös nevezőre hozni: keressük a név, PTS, AST, REB oszlopokat
            colmap = {}
            for c in df0.columns:
                cname = str(c).lower()
                if "player" in cname or "name" in cname or "jug" in cname:
                    colmap[c] = "Játékos (Player)"
                if "pts" in cname or "points" in cname or re.search(r"\bpt\b", cname):
                    colmap[c] = "Pont (Points)"
                if "ast" in cname or "assists" in cname:
                    colmap[c] = "Assziszt (Assists)"
                if "reb" in cname or "rbs" in cname or "rebound" in cname:
                    colmap[c] = "Lepattanó (Rebounds)"
            # csak a releváns oszlopok megtartása
            keep = [c for c in df0.columns if c in colmap]
            if not keep:
                # ha nincs, adunk legalább az első két oszlopot
                keep = list(df0.columns[:4])
            df_trim = df0[keep].rename(columns=colmap)
            # ha nincs Csapat mező, adjunk üreset
            if "Csapat (Team)" not in df_trim.columns:
                df_trim.insert(0, "Csapat (Team)", "?")
            return df_trim
        except Exception:
            return None
    except Exception:
        return None


# -----------------------
# Felhasználói felület
# -----------------------
st.markdown("Válaszd ki a mérkőzés napját (a dátum a mérkőzés napjára vonatkozik). Írj be egy tetszőleges csapatnevet (részleges név is jó).")
selected_date = st.date_input("Dátum (mérkőzés napja):", value=date.today())
team_query = st.text_input("Csapat neve (pl. Partizan, Bayern, Bayern München, Szolnok):")

if st.button("Keresés"):
    if not team_query or team_query.strip() == "":
        st.warning("Adj meg egy csapatnevet!")
    else:
        st.info("Lekérdezem a napi meccslistát... (először JSON feed, majd HTML fallback)")
        daily_json = fetch_daily_json_feed(selected_date)
        matches = []
        if daily_json:
            matches = parse_matches_from_daily_json(daily_json)

        if not matches:
            # fallback: napi HTML oldal
            matches = fetch_daily_html_matches(selected_date)

        if not matches:
            st.error("Nem található meccs az adott napon (vagy a forrás nem elérhető).")
        else:
            # filter a felhasználó által bevitt csapatnévre (részleges egyezés, kis-/nagybetű érzéketlen)
            filtered = filter_matches_by_team(matches, team_query)
            if not filtered:
                st.error("A megadott névhez nem található meccs ezen a napon. Próbáld más írásmóddal.")
            else:
                st.success(f"{len(filtered)} találat a megadott csapatnév alapján.")
                # Mutassuk fel a találatokat választásra
                options = []
                for m in filtered:
                    score_display = ""
                    if m.get("home_score") is not None and m.get("away_score") is not None:
                        score_display = f"{m.get('home_score')} - {m.get('away_score')}"
                    else:
                        score_display = m.get("score_text") or "?"
                    label = f"{m.get('home')}  –  {m.get('away')}   ({score_display})"
                    options.append((label, m))

                # Kiválasztás rádiógombokkal
                labels = [opt[0] for opt in options]
                idx = st.radio("Válaszd ki a pontos mérkőzést:", list(range(len(labels))), format_func=lambda i: labels[i])
                chosen = options[idx][1]

                st.markdown("### Kiválasztott mérkőzés")
                st.write(f"**{chosen.get('home')} – {chosen.get('away')}**")
                home_s = chosen.get("home_score")
                away_s = chosen.get("away_score")
                if home_s is not None and away_s is not None:
                    st.success(f"Eredmény: {home_s} – {away_s}")
                else:
                    st.success(f"Eredmény: {chosen.get('score_text','?')}")

                st.markdown("---")
                st.markdown("### Statisztika lekérése (első kör: JSON feed; fallback: HTML scrape)")

                match_id = chosen.get("match_id")
                stats_df = None

                # 1) próbáljuk a részletes JSON feedet
                if match_id:
                    st.info("Megpróbálom a Flashscore részletes JSON feedjét...")
                    detail_json = fetch_match_json_detail(match_id)
                    if detail_json:
                        stats_df = parse_player_stats_from_match_json(detail_json)
                        if stats_df is not None:
                            st.success("Részletes statisztika betöltve (JSON feed).")
                # 2) fallback HTML scrape
                if stats_df is None:
                    st.info("A JSON feed nem adott játékosstatisztikát vagy nem elérhető — HTML fallback következik...")
                    stats_df = fetch_match_stats_by_html(match_id)

                    if stats_df is not None:
                        st.success("Részletes statisztika betöltve (HTML scrape).")

                # 3) Ha nincs stat
                if stats_df is None:
                    st.error("Statisztika betöltése sikertelen")
                else:
                    # Győződjünk meg róla, hogy a kívánt oszlopnevek megvannak (magyar(angol))
                    # Átrendezzük: Csapat, Játékos, Pont, Assziszt, Lepattanó
                    cols_map = {
                        "Csapat (Team)": "Csapat (Team)",
                        "Játékos (Player)": "Játékos (Player)",
                        "Pont (Points)": "Pont (Points)",
                        "Assziszt (Assists)": "Assziszt (Assists)",
                        "Lepattanó (Rebounds)": "Lepattanó (Rebounds)"
                    }
                    # Ha az oszlopok más nyelven jönnek, próbáljuk normalizálni (kis- és angol címkék)
                    df = stats_df.copy()
                    # Normálás: ha csak angol van (Points), hozzáadunk magyar(angol) oszlopnevet
                    rename_map = {}
                    for c in df.columns:
                        lc = c.lower()
                        if lc in ("team", "teamname"):
                            rename_map[c] = "Csapat (Team)"
                        if lc in ("player", "player name", "name"):
                            rename_map[c] = "Játékos (Player)"
                        if "point" in lc or "pts" in lc or re.match(r"^p(ts)?$", lc):
                            rename_map[c] = "Pont (Points)"
                        if "assist" in lc or "ast" in lc:
                            rename_map[c] = "Assziszt (Assists)"
                        if "reb" in lc or "rebound" in lc:
                            rename_map[c] = "Lepattanó (Rebounds)"
                    if rename_map:
                        df = df.rename(columns=rename_map)

                    # Biztosítsuk a meglévő kulcsokat
                    for want in cols_map.values():
                        if want not in df.columns:
                            df[want] = "?"

                    display_cols = list(cols_map.values())
                    st.dataframe(df[display_cols].fillna("?"))
                    st.markdown("**Megjegyzés:** A statisztika betöltése nem hivatalos scraping/privát feed alapján történt; ha nem látszik minden mező, az adott forrás nem szolgáltatta azokat.")

st.markdown("---")
st.markdown("Források: Flashscore (rejtett JSON feed és HTML), best-effort scraping. Ha szeretnéd, hozzáadok további forrásokat (Sofascore, Euroleague API stb.).")
