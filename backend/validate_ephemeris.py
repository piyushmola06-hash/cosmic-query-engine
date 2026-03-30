"""
Validate Swiss Ephemeris (pyswisseph) installation.

Calculates Moon and Sun positions for 15 March 1990 at 10:30 AM
using the local ephemeris data files in ./backend/ephe/.
"""

import sys


def validate() -> None:
    """Run ephemeris validation and print results."""
    try:
        import swisseph as swe
    except ImportError as e:
        print(f"ERROR: Could not import swisseph — {e}")
        print("Run: pip install pyswisseph")
        sys.exit(1)

    try:
        swe.set_ephe_path("./backend/ephe")

        # 15 March 1990, 10:30 AM → decimal hours = 10.5
        jd = swe.julday(1990, 3, 15, 10.5)
        print(f"Julian Day for 1990-03-15 10:30 AM UT: {jd:.6f}")
        print()

        # Moon (body ID: swe.MOON)
        moon_result, moon_flags = swe.calc_ut(jd, swe.MOON)
        moon_longitude = moon_result[0]
        moon_latitude = moon_result[1]
        moon_distance = moon_result[2]
        print(f"Moon longitude : {moon_longitude:.6f}°")
        print(f"Moon latitude  : {moon_latitude:.6f}°")
        print(f"Moon distance  : {moon_distance:.6f} AU")
        print()

        # Sun (body ID: swe.SUN)
        sun_result, sun_flags = swe.calc_ut(jd, swe.SUN)
        sun_longitude = sun_result[0]
        sun_latitude = sun_result[1]
        sun_distance = sun_result[2]
        print(f"Sun longitude  : {sun_longitude:.6f}°")
        print(f"Sun latitude   : {sun_latitude:.6f}°")
        print(f"Sun distance   : {sun_distance:.6f} AU")
        print()

        print("Swiss Ephemeris OK")

    except Exception as e:
        print(f"ERROR: Ephemeris calculation failed — {e}")
        sys.exit(1)


if __name__ == "__main__":
    validate()
