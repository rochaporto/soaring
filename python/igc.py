import optparse
import sys

from datetime import datetime, timedelta
from math import sin, cos, asin, acos, atan2, fabs, sqrt, radians, degrees, pi
from optparse import OptionParser

verbose = False

class FlightBase(object):
    
    earthRadius = 6371

    def __init__(self, verbose=False):
        self.verbose = True

    def verbose(self, str):
        if self.verbose:
            print str

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
        return 2 * asin( 
                sqrt( (sin( (p1["latrd"] - p2["latrd"]) / 2 ) ) ** 2 
                    + cos(p1["latrd"]) * cos(p2["latrd"]) * ( sin( (p1["lonrd"] - p2["lonrd"]) / 2 ) ) ** 2
                    )
                ) * self.earthRadius

    def bearing(self, p1, p2):
        return degrees(
                atan2( 
                    sin(p1["lonrd"] - p2["lonrd"]) * cos(p2["latrd"]), 
                    cos(p1["latrd"]) * sin(p2["latrd"]) 
                    - sin(p1["latrd"]) * cos(p2["latrd"]) * cos(p1["lonrd"] - p2["lonrd"])
                ) % (2 * pi)
                )

class Flight(FlightBase):
    """
    Flight metadata: 
      dte (date), fxa (fix accuracy), plt (pilot), cm2 (crew 2), gty (glider type),
      gid (glider reg number), dtm (gps datum), rfw (logger firmware revision),
      rhw (logger revision number), fty (logger mfr and model), gps (gps mfr / model),
      prs (pressure sensor description), cid (competition id), ccl (glider class)
    """

    STOPPED = 0
    STRAIGHT = 1
    CIRCLING = 2

    def __init__(self):
        self.metadata = {
            "mfr": None, "mfrId": None, "mfrIdExt": None,
            "dte": None, "fxa": None, "plt": None, "cm2": None, "gty": None,
            "gid": None, "dtm": None, "rfw": None, "rhw": None, "fty": None,
            "gps": None, "prs": None, "cid": None, "ccl": None
        }
        self.control = {
            "minSpeed": 50.0, "minCircleRate": 4, "minCircleTime": 45, "minStraightTime": 15,
        }
        self.points = []
        self.phases = []
        self.stats = {
            "totalKms": 0.0, "maxAlt": None, "minAlt": None, "maxGSpeed": None, "minGSpeed": None,
        }

    def putPoint(self, time, lat, lon, fix, pAlt, gAlt):
        p = {
            "time": time, "lat": lat, "lon": lon, "fix": fix, "pAlt": pAlt, "gAlt": gAlt,
            "latdg": None, "londg": None, "latrd": None, "lonrd": None,
            "computeL2": {
                "distance": None, "bearing": None, "timeDelta": None, "pAltDelta": None, "gAltDelta": None,
            },
            "computeL3": {
                "gSpeed": None, "pVario": None, "gVario": None, "turnRate": None,
            },
            "computeL4": {
                "mode": Flight.STOPPED,
            },
            }
        prevP = self.points[-1] if len(self.points) != 0 else None
        self.computeL1(p)
        if prevP is not None:
            self.computeL2(prevP, p)
            self.computeL3(prevP, p)
            self.computeStats(p)
        self.points.append(p)

    def computeL1(self, p):
        p["latdg"] = self.dms2dd(p["lat"])
        p["londg"] = self.dms2dd(p["lon"])
        p["latrd"] = radians(p["latdg"])
        p["lonrd"] = radians(p["londg"])

    def computeL2(self, prevP, p):
        p["computeL2"]["distance"] = self.distance(prevP, p)
        p["computeL2"]["bearing"] = self.bearing(prevP, p)
        p["computeL2"]["timeDelta"] = (p["time"] - prevP["time"]).seconds
        p["computeL2"]["pAltDelta"] = p["pAlt"] - prevP["pAlt"]
        p["computeL2"]["gAltDelta"] = p["gAlt"] - prevP["gAlt"]

    def computeL3(self, prevP, p):
        p["computeL3"]["gSpeed"] = (p["computeL2"]["distance"] * 3600) / p["computeL2"]["timeDelta"]
        p["computeL3"]["pVario"] = float(p["computeL2"]["pAltDelta"]) / p["computeL2"]["timeDelta"]
        p["computeL3"]["gVario"] = float(p["computeL2"]["gAltDelta"]) / p["computeL2"]["timeDelta"]
        if prevP["computeL2"]["bearing"] is not None:
            p["computeL3"]["turnRate"] = (p["computeL2"]["bearing"] \
                - prevP["computeL2"]["bearing"]) / p["computeL2"]["timeDelta"]

    def computeL4(self, prevP, p):
        self.computeMode(p)
        
    def computeStats(self, p):
        if p["computeL4"]["mode"] is Flight.STOPPED:
            return
        self.stats["totalKms"] += p["computeL2"]["distance"]
        self.stats["maxAlt"] = max(self.stats["maxAlt"], p["pAlt"])
        self.stats["minAlt"] = p["pAlt"] if self.stats["minAlt"] is None \
            else min(self.stats["minAlt"], p["pAlt"])
        self.stats["maxGSpeed"] = max(self.stats["maxGSpeed"], p["computeL3"]["gSpeed"])
        self.stats["minGSpeed"] = p["computeL3"]["gSpeed"] if self.stats["minGSpeed"] is None \
            else min(self.stats["minGSpeed"], p["computeL3"]["gSpeed"])

    def computeMode(self, points):
        # First point, just set as stopped and return
        if len(self.points) == 0:
            self.points[0]["computeL4"]["mode"] = Flight.STOPPED
            p["computeL4"]["mode"] = Flight.STOPPED
            return
        i = len(self.points) - 1
        # Move from stopped to straight
        if self.points[i]["computeL4"]["mode"] == Flight.STOPPED and p["computeL3"]["gSpeed"] > self.control["minSpeed"]:
            p["computeL4"]["mode"] = Flight.STRAIGHT
        # Move from straight to circling (>= minTurnRate kept for more than minCircleTime)
        elif p["computeL4"]["mode"] == Flight.STRAIGHT:
            curTime, testP = p["time"], self.points[i]
            while i > 0 and (curTime - testP["time"]).seconds < self.control["minCircleTime"]:
                if fabs(testP["computeL3"]["turnRate"]) >= self.control["minCircleRate"]:
                    --i
                    testP = self.points[i]
                else:
                    return
            for j in range(i, len(self.points)-1):
                self.points[j]["computeL4"]["mode"] = Flight.CIRCLING
            p["computeL4"]["mode"] = Flight.CIRCLING
            # close previous phase
        # Move from circling to straight (< minTurnRate for more than minStraightTime)
        elif p["computeL4"]["mode"] == Flight.CIRCLING:
            curTime, testP = p["time"], self.points[i]
            while i > 0 and (curTime - testP["time"]).seconds < self.control["minStraightTime"]:
                if fabs(testP["computeL3"]["turnRate"]) < self.control["minCircleRate"]:
                    --i
                    testP = self.points[i]
                else:
                    return
            for j in range(i, len(self.points)-1):
                self.points[j]["computeL4"]["mode"] = Flight.STRAIGHT
            p["computeL4"]["mode"] = Flight.STRAIGHT
            # close previous phase

class FlightFetcherType:
    FILE = 1
    URL = 2

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
        self.flight.putPoint(datetime.strptime(record[1:7], "%H%M%S"), record[7:15], record[15:24],
                record[24], int(record[25:30]), int(record[30:35]))

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
