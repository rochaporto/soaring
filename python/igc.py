import optparse
import sys

from datetime import datetime, timedelta
from math import sin, cos, asin, acos, fabs, sqrt, radians, pi
from optparse import OptionParser

verbose = False

class FlightBase(object):
    
    earthRadius = 6371

    def __init__(self, verbose=False):
        self.verbose = True

    def verbose(self, str):
        if self.verbose:
            print str

    def dg2rd(self, dg):
        return radians(dg)

    def dms2dd(self, value):
        cardinal = value[-1]
        dd = None
        if cardinal in ('N', 'S'):
            dd = float(value[0:2]) + ( ( float(value[2:4]) + (float(value[4:7]) / 1000.0)) / 60.0 )
        else:
            dd = float(value[0:3]) + ( ( float(value[3:5]) + (float(value[5:8]) / 1000.0)) / 60.0 )
        if cardinal in ('S', 'W'):
            dd *= -1
        return dd

    def distance(self, p1, p2):
#        return 2 * asin( 
#                sqrt( (sin( (p1["latrd"] - p2["latrd"]) / 2 ) ) ** 2 
#                    + cos(p1["latrd"]) * cos(p2["latrd"]) * ( sin( (p1["lonrd"] - p2["lonrd"]) / 2 ) ) ** 2
#                    )
#                )
        return acos ( sin(p1["latrd"]) * sin(p2["latrd"]) + cos(p1["latrd"]) * cos(p2["latrd"]) * cos(p1["lonrd"]-p2["lonrd"])) * self.earthRadius

class Flight(FlightBase):
    """
    Flight metadata: 
      dte (date), fxa (fix accuracy), plt (pilot), cm2 (crew 2), gty (glider type),
      gid (glider reg number), dtm (gps datum), rfw (logger firmware revision),
      rhw (logger revision number), fty (logger mfr and model), gps (gps mfr / model),
      prs (pressure sensor description), cid (competition id), ccl (glider class)
    """

    def __init__(self):
        self.metadata = {
            "mfr": None, "mfrId": None, "mfrIdExt": None,
            "dte": None, "fxa": None, "plt": None, "cm2": None, "gty": None,
            "gid": None, "dtm": None, "rfw": None, "rhw": None, "fty": None,
            "gps": None, "prs": None, "cid": None, "ccl": None
        }
        self.points = []
        self.stats = {
            "totalKms": 0.0, "pressAlt+": 0, "pressAlt-": 0, "time+": 0, "time-": 0, 
            "pressAlt+": 0, "pressAlt-": 0, "gnssAlt+": 0, "gnssAlt-": 0,
        }

    def addPoint(self, p):
        prevP = self.points[-1] if len(self.points) != 0 else None
        p["latdg"] = self.dms2dd(p["lat"])
        p["londg"] = self.dms2dd(p["lon"])
        p["latrd"] = self.dg2rd(p["latdg"])
        p["lonrd"] = self.dg2rd(p["londg"])
        # do basic analysis immediatelly
        p["timeDiff"], p["pressAltDiff"], p["gnssAltDiff"], p["dist"], p["pressVario"], p["gnssVario"] = 0, 0, 0, 0, 0, 0
        if prevP is not None:
            p["timeDiff"] = (p["time"] - prevP["time"]).seconds
            p["pressAltDiff"] = fabs(p["pressAlt"] - prevP["pressAlt"])
            p["gnssAltDiff"] = fabs(p["gnssAlt"] - prevP["gnssAlt"])
            p["dist"] = self.distance(p, prevP)
            p["pressVario"] =  float(p["pressAltDiff"]) / p["timeDiff"]
            p["gnssVario"] = float(p["gnssAltDiff"]) / p["timeDiff"]
        self.points.append(p)

        # do basic stats immediatelly
        if p["pressVario"] > 0:
            self.stats["time+"] += p["timeDiff"]
            self.stats["pressAlt+"] += p["pressAltDiff"]
            self.stats["gnssAlt+"] += p["gnssAltDiff"]
        else:
            self.stats["time-"] += p["timeDiff"]
            self.stats["pressAlt-"] += p["pressAltDiff"]
            self.stats["gnssAlt-"] += p["gnssAltDiff"]
        self.stats["totalKms"] += p["dist"]

class FlightFetcherType:
    FILE=1
    URL=2

class FlightFetcher(FlightBase):

    def __init__(self, location, fetcherType=FlightFetcherType.FILE):
        self.location = location
        self.fetcherType = fetcherType
        self.rawContent = None
        self.verbose("Loading flight from : %s" % self.location)

    def getRawContent(self):
        if self.rawContent is None: # Load the contents and store
            if self.fetcherType == FlightFetcherType.FILE:
                self.verbose("Fetcher mode: FILE :: opening '%s'" % self.location)
                f = open(self.location, 'r')
                self.rawContent = f.read()
                f.close()
            elif type == FlightFetcherType.URL: #TODO
                None
        return self.rawContent

class FlightReader(FlightBase):
    """
        Creates a Flight object from the data taken from the given FlightFetcher.
    """

    def __init__(self, flightFetcher, autoParse=True):
        self.flightFetcher = flightFetcher
        self.flight = Flight()
        self.flight.rawFlight = self.flightFetcher.getRawContent()
        if autoParse:
            self.parse()

    def parse(self):
        """
            http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
        """
        lines = self.flight.rawFlight.split("\r\n")
        for line in lines:
            getattr(self, "parse%s" % line[0])(line)

    def parseA(self, record):
        self.flight.metadata["mfr"] = record[1:4]
        self.flight.metadata["mfrId"] = record[4:7]
        self.flight.metadata["mfrIdExt"] = record[7:]

    def parseB(self, record):
        p = {"time": datetime.strptime(record[1:7], "%H%M%S"),
             "lat": record[7:15], "lon": record[15:24], 
             "fix": record[24], "pressAlt": int(record[25:30]), "gnssAlt": int(record[30:35])}
        self.flight.addPoint(p)

    def parseC(self, record):
        None

    def parseF(self, record):
        None

    def parseG(self, record):
        None

    def parseH(self, record):
        hType = record[2:5].lower()
        if hType == 'dte':
            self.flight.metadata['dte'] = datetime.strptime(record[5:], "%d%m%y")
        elif hType == 'fxa':
            self.flight.metadata[hType] = record[5:]
        else:
            self.flight.metadata[hType] = record[record.find(':')+1:]

    def parseI(self, record):
        None

    def parseL(self, record):
        None

class FlightExporter(FlightBase):

    def __init__(self, flight):
        self.flight = flight

    def export(self):
        print """
        Date: %s\tPilot: %s
        Registration: %s\tType: %s\t\tClass: %s
        Points: %d
        """ % (self.flight.metadata["dte"].strftime("%Y-%m-%d"), 
        self.flight.metadata["plt"], self.flight.metadata["gid"],
        self.flight.metadata["gty"], self.flight.metadata["ccl"], 
        len(self.flight.points))
        print self.flight.stats

class FlightCmdLine(object):

    usage = "usage: %prog [options] args"
    
    version = 0.1

    description = "Flight parser tool"

    def __init__(self):
        self.optParser = OptionParser(usage=self.usage, version=self.version,
                description=self.description)
        self.optParser.add_option("-v", "--verbose",
                action="store_true", dest="verbose",
                default=False, help="make lots of noise")

        (self.options, self.args) = self.optParser.parse_args()
        
        if len(self.args) != 1:
            self.optParser.error("Wrong number of arguments given")

        verbose = self.options.verbose 

    def run(self):
        flightFetcher = FlightFetcher(self.args[0])
        flightReader = FlightReader(flightFetcher)
        FlightExporter(flightReader.flight).export()

if __name__ == "__main__":
    flightCmd = FlightCmdLine()
    sys.exit(flightCmd.run())
