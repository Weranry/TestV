from ..lib.date_calculator import DateCalculator


def to_json(**kwargs):
    tz = kwargs.get('tz')
    dc = DateCalculator(tz)
    return {
        'solar': dc.get_solar_date(),
        'lunar': dc.get_lunar_date(),
        'ganzhi': dc.get_ganzhi_date(),
        'season': dc.get_season_info(),
        'festival': dc.get_festival_info()
    }
