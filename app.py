import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.title("Nemzetközi kosárlabda mérkőzésstatisztika")

# --- INPUTOK ---
date = st.date_input("Meccs dátuma")
league = st.selectbox(
    "Bajnokság",
    ["NBA", "EuroLeague", "Spain ACB", "Italy LegaBasket", "Hungary NB I", "FIBA"]
)
teams = st.text_input("Csapatok (pl.: 'Real Madrid vs Barcelona')")

# --------------------------
# NBA API adapter
# --------------------------
def fetch_nba(date, teams):
    try:
        from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv2

        date_str = date.strftime("%Y-%m-%d")
        sb = scoreboardv2.ScoreboardV2(game_date=date_str)
        games = sb.get_data_frames()[0]

        try:
            t1, _, t2 = teams.split()
        except:
            return None, None, "NBA.com"

        match = games[
            ((games['HOME_TEAM_ABBREVIATION'] == t1) & (games['VISITOR_TEAM_ABBREVIATION'] == t2)) |
            ((games['HOME_TEAM_ABBREVIATION'] == t2) & (games['VISITOR_TEAM_ABBREVIATION'] == t1))
        ]

        if match.empty:
            return None, None, "NBA.com"

        game_id = match.iloc[0]['GAME_ID']
        result = {
            "home": match.iloc[0]['HOME_TEAM_ABBREVIATION'],
            "away": match.iloc[0]['VISITOR_TEAM_ABBREVIATION'],
            "home_pts": match.iloc[0]['PTS_HOME'],
            "away_pts": match.iloc[0]['PTS_AWAY']
        }

        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        players = box.get_data_frames()[0]

        cols = ['TEAM_ABBREVIATION','PLAYER_NAME','MIN','PTS','AST','REB','FG_PCT','FG3_PCT','FT_PCT']
        return result, players[cols], "NBA.com (hivatalos)"

    except Exception:
        return None, None, "NBA.com"


# --------------------------
# SOFASCORE fallback (minden más ligára)
# --------------------------
def fetch_from_sofascore(date, teams):
    """
    Sofascore nem ad publikus API-t, de JSON endpointok vannak.
    Ezzel próbálkozunk, ha nincs NBA adat.
    """
    try:
        t1, _, t2 = teams.split()
    except:
        return None, None, "Sofascore"

    # Dátum iso formátum
    date_str = date.strftime("%Y-%m-%d")

    # Sofascore kereső endpoint
    search_url = f"https://api.sofascore.com/api/v1/search/events?q={t1}%20{t2}"

    try:
        r = requests.get(search_url, timeout=5)
        if r.status_code != 200:
            return None, None, "Sofascore"
        data = r.json()
    except:
        return None, None, "Sofascore"

    if "events" not in data or len(data["events"]) == 0:
        return None, None, "Sofascore"

    # megpróbálunk dátum alapján szűrni
    match = None
    for e in data["events"]:
        if "startTimestamp" not in e:
            continue
        t = datetime.fromtimestamp(e["startTimestamp"])
        if t.strftime("%Y-%m-%d") == date_str:
            match = e
            break

    if match is None:
        return None, None, "Sofascore"

    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]
    home_pts = match.get("homeScore", {}).get("current")
    away_pts = match.get("awayScore", {}).get("current")

    result = {
        "home": home,
        "away": away,
        "home_pts": home_pts,
        "away_pts": away_pts
    }

    # ------------------
    # Sofascore nem mindig ad részletes boxscore-t → megpróbáljuk
    # ------------------
    event_id = match["id"]
    box_url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"

    try:
        r2 = requests.get(box_url, timeout=5)
        if r2.status_code != 200:
            return result, None, "Sofascore"
        stats_json = r2.json()

        if "statistics" not in stats_json:
            return result, None, "Sofascore"

        # Átalakítjuk DataFrame-be
        rows = []
        for teamstat in stats_json["statistics"]:
            team_name = teamstat.get("team", {}).get("name", "N/A")
            for s in teamstat.get("groups", []):
                for item in s.get("statisticsItems", []):
                    rows.append({
                        "TEAM": team_name,
                        "STAT": item.get("name"),
                        "VALUE": item.get("value")
                    })

        if len(rows) == 0:
            return result, None, "Sofascore"

        df = pd.DataFrame(rows)
        return result, df, "Sofascore"

    except:
        return result, None, "Sofascore"


# -------------------------------------
# Lekérdezés gomb
# -------------------------------------
if st.button("Lekérdezés"):
    if not teams:
        st.warning("Add meg a csapatokat!")
        st.stop()

    st.write(f"Dátum: **{date}**, Liga: **{league}**")

    # 1) NBA (csak ha NBA-t választottak)
    if league == "NBA":
        result, stats, source = fetch_nba(date, teams)
        if result is None:
            st.error("Statisztika betöltése sikertelen")
        else:
            st.subheader(f"Forrás: {source}")
            st.success(f"{result['away']} @ {result['home']} — {result['away_pts']} : {result['home_pts']}")

            if stats is not None:
                st.subheader("Játékos statisztikák")
                st.dataframe(stats)
            else:
                st.error("Statisztika betöltése sikertelen")

    else:
        # 2) Minden más liga → Sofascore fallback
        result, stats, source = fetch_from_sofascore(date, teams)

        st.subheader(f"Forrás: {source}")

        if result is None:
            st.error("Statisztika betöltése sikertelen")
        else:
            st.success(f"{result['away']} @ {result['home']} — {result['away_pts']} : {result['home_pts']}")

            if stats is not None:
                st.subheader("Statisztikák")
                st.dataframe(stats)
            else:
                st.error("Statisztika betöltése sikertelen")
