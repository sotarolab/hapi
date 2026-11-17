"""The points the site shows, with their coordinates. site.py builds a page per point; weather.py fetches the
weather forecast at each."""

# lid: (name, lat, lon). Flood gauges carry their USGS id; their NWS flood categories come from live.py.
# fmt: off
RESERVOIRS = {
    "LAMC1": ("Lake Mendocino", 39.197, -123.186), "ORDC1": ("Oroville", 39.540, -121.493),
    "SHDC1": ("Shasta", 40.718, -122.420), "FOLC1": ("Folsom", 38.683, -121.183),
    "NBBC1": ("New Bullards Bar", 39.393, -121.140), "NMSC1": ("New Melones", 37.948, -120.525),
    "FRAC1": ("Millerton", 37.001, -119.705), "EXQC1": ("McClure", 37.585, -120.270),
    "ISAC1": ("Isabella", 35.646, -118.473), "TMDC1": ("Kaweah", 36.415, -119.002),
    "SCSC1": ("Success", 36.057, -118.924), "WSDC1": ("Lake Sonoma", 38.723, -123.010),
    "NDPC1": ("Don Pedro", 37.702, -120.421), "CEGC1": ("Trinity", 40.801, -122.762),
    "INVC1": ("Indian Valley", 39.083, -122.533),
}
GAUGES = {
    "HOPC1": ("Russian River near Hopland", 39.027, -123.131, "11462500"),
    "HEAC1": ("Russian River near Healdsburg", 38.613, -122.836, "11464000"),
    "GUEC1": ("Russian River at Guerneville", 38.499, -122.998, "11467002"),
    "NVRC1": ("Navarro River near Navarro", 39.170, -123.668, "11468000"),
    "FTSC1": ("Eel River near Fort Seward", 40.218, -123.633, "11475000"),
    "SCOC1": ("Eel River near Scotia", 40.491, -124.100, "11477000"),
    "LEGC1": ("South Fork Eel River near Leggett", 39.875, -123.721, "11475800"),
    "BRGC1": ("Van Duzen River near Bridgeville", 40.480, -123.891, "11478500"),
    "ARCC1": ("Mad River near Arcata", 40.910, -124.061, "11481000"),
    "ORIC1": ("Redwood Creek near Orick", 41.299, -124.051, "11482500"),
    "FTDC1": ("Smith River at Dr Fine Bridge", 41.881, -124.136, "11532650"),
    "MHBC1": ("Cosumnes River at Michigan Bar", 38.500, -121.045, "11335000"),
}
# fmt: on
