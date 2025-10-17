import psycopg2
from psycopg2.extras import RealDictCursor

def get_player_data_from_db(
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
    season_year: int = None
):
    """
    Fetch player metadata (name, position, team, tier) from a PostgreSQL database.

    Args:
        host (str): Database hostname or IP
        port (int): Database port (e.g., 5432)
        dbname (str): Database name
        user (str): Database username
        password (str): Database password
        season_year (int, optional): Filter by a specific season year if desired

    Returns:
        list[dict]: Player records, e.g.
            [
                {"player_name": "Harrison Jr., Marvin", "position": "WR", "team": "ARI", "tier": 1},
                {"player_name": "Fehoko, Simi", "position": "WR", "team": "ARI", "tier": 2},
                ...
            ]
    """
    query = """
        SELECT
            p.player_name,
            p.position,
            t.abbreviation AS team,
            ps.tier
        FROM public.players p
        LEFT JOIN public.teams t ON p.team_id = t.team_id
        LEFT JOIN public.player_seasons ps ON ps.player_id = p.player_id
        LEFT JOIN public.seasons s ON ps.season_id = s.season_id
    """

    # Optionally filter by season if provided
    if season_year:
        query += " WHERE s.year = %s"

    conn = None
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if season_year:
                cur.execute(query, (season_year,))
            else:
                cur.execute(query)
            rows = cur.fetchall()

        # Convert to a simple Python list of dicts
        player_data = [
            {
                "player_name": row["player_name"],
                "position": row["position"],
                "team": row["team"],
                "tier": row["tier"],
            }
            for row in rows
        ]
        return player_data

    except Exception as e:
        print(f"Error fetching player data: {e}")
        return []

    finally:
        if conn:
            conn.close()
