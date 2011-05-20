import optparse
import urllib2
import sys

from datetime import datetime, timedelta
from math import sin, cos, asin, acos, atan2, fabs, sqrt, radians, degrees, pi
from optparse import OptionParser

from common import Base

class FlightBase(Base):
    
    # FAI Earth Sphere Radius
    earthRadius = 6371 

    def __init__(self):
        None

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

    STOPPED, STRAIGHT, CIRCLING = range(3)

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
        self.updateMode()

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

    def computeStats(self, p):
        self.stats["totalKms"] += p["computeL2"]["distance"]
        self.stats["maxAlt"] = max(self.stats["maxAlt"], p["pAlt"])
        self.stats["minAlt"] = p["pAlt"] if self.stats["minAlt"] is None \
            else min(self.stats["minAlt"], p["pAlt"])
        self.stats["maxGSpeed"] = max(self.stats["maxGSpeed"], p["computeL3"]["gSpeed"])
        self.stats["minGSpeed"] = p["computeL3"]["gSpeed"] if self.stats["minGSpeed"] is None \
            else min(self.stats["minGSpeed"], p["computeL3"]["gSpeed"])

    def newPhase(self, pIndex, phaseType):
        if len(self.phases) != 0:
            self.phases[-1]["end"] = pIndex - 1
        self.phases.append({"start": pIndex, "end": None, "type": phaseType})
        # TODO: calculate phase stats?

    def updateMode(self):
        # First point, just set as stopped and return
        if len(self.points) == 1:
            self.points[0]["computeL4"]["mode"] = Flight.STOPPED
            return

        p, pI = self.points[-1], len(self.points) - 1
        p["computeL4"]["mode"] = self.points[-2]["computeL4"]["mode"]
        # Move from stopped to straight
        if p["computeL4"]["mode"] == Flight.STOPPED \
            and p["computeL3"]["gSpeed"] > self.control["minSpeed"]:
            p["computeL4"]["mode"] = Flight.STRAIGHT
            self.newPhase(pI, Flight.STRAIGHT)
        # Move from straight to circling (>= minTurnRate kept for more than minCircleTime)
        elif p["computeL4"]["mode"] == Flight.STRAIGHT:
            curTime, j = p["time"], pI-1
            while j > 0 and (p["time"] - self.points[j]["time"]).seconds < self.control["minCircleTime"]:
                if fabs(self.points[j]["computeL3"]["turnRate"]) >= self.control["minCircleRate"]:
                    j -= 1
                else:
                    return
            for g in range(j, pI+1):
                self.points[g]["computeL4"]["mode"] = Flight.CIRCLING
            self.newPhase(pI, Flight.CIRCLING)
        # Move from circling to straight (< minTurnRate for more than minStraightTime)
        elif p["computeL4"]["mode"] == Flight.CIRCLING:
            curTime, j = p["time"], pI-1
            while j > 0 and (curTime - self.points[j]["time"]).seconds < self.control["minStraightTime"]:
                if fabs(self.points[j]["computeL3"]["turnRate"]) < self.control["minCircleRate"]:
                    j -= 1
                else:
                    return
            for g in range(j, pI+1):
                self.points[g]["computeL4"]["mode"] = Flight.STRAIGHT
            self.newPhase(pI, Flight.STRAIGHT)

    def pathInKml(self):
        pathKml = ""
        for point in self.points:
            pathKml += "%.2f,%.2f,%d " % (point["latdg"], point["londg"], point["gAlt"])
        return "<LineString><coordinates>%s</coordinates></LineString>" % pathKml

class FlightFetcher(FlightBase):

    def __init__(self, uri):
        self.uri = uri
        self.rawContent = None

    def fetch(self):
        self.verbose("Fetching flight from : %s" % self.uri)
        self.raw = urllib2.urlopen(self.uri).read()
        return self.raw

class FlightReader(FlightBase):
    """
        Creates a Flight object from the data taken from the given FlightFetcher.
    """

    def __init__(self, rawFlight, autoParse=True):
        self.flight = Flight()
        self.flight.rawFlight = rawFlight
        if autoParse:
            self.parse()

    def parse(self):
        """
            http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
        """
        lines = self.flight.rawFlight.split("\n")
        for line in lines:
            if line != "":
                getattr(self, "parse%s" % line[0])(line.strip())

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

class FlightOptimizer(FlightBase):

    def __init__(self, flight):
        self.flight = flight
        self.maxCPDistance = 0 # Maximum distance between 2 consecutive points
        self.prepare()

    def prepare(self):
        for i in range(0, len(self.flight.points)-1):
            distance = self.distance(self.flight.points[i], self.flight.points[i+1])
            if distance > self.maxCPDistance:
                self.maxCPDistance = distance

    def forward(self, i, distance):
        step = int(distance / self.maxCPDistance)
        if step > 0:
            return i + step
        return i+1

    def optimize1(self):
        circuit = {"sta": None, "tps": None, "end": None, "distance": 0.0}
        flight, nPoints = self.flight, len(self.flight.points)
        sta, tp1, end = 0, 1, nPoints-1
        while tp1 < nPoints-1:
            distance = self.distance(flight.points[sta], flight.points[tp1]) \
                + self.distance(flight.points[tp1], flight.points[end])
            if distance > circuit["distance"]:
                circuit = {"sta": sta, "tps": [tp1], "end": end, "distance": distance}
                tp1 += 1
                print circuit
            else:
                tp1 = self.forward(tp1, 0.5 * (circuit["distance"] - distance))
        return circuit

    def optimize2(self):
        circuit = {"sta": None, "tps": None, "end": None, "distance": 0.0}
        flight, nPoints = self.flight, len(self.flight.points)
        sta, tp1, tp2, end = 0, 1, -1, nPoints-1
        for tp1 in range(1, nPoints-2):
            leg1 = self.distance(flight.points[sta], flight.points[tp1])
            tp2 = tp1+1
            while tp2 < nPoints-1:
                distance = leg1 + self.distance(flight.points[tp1], flight.points[tp2]) \
                    + self.distance(flight.points[tp2], flight.points[end])
                if distance > circuit["distance"]:
                    circuit = {"sta": sta, "tps": [tp1, tp2], "end": end, "distance": distance}
                    tp2 += 1
                    print circuit
                else:
                    tp2 = self.forward(tp2, 0.5 * (circuit["distance"] - distance))
        return circuit

    def optimize3(self):
        circuit = {"sta": None, "tps": None, "end": None, "distance": 0.0}
        flight, nPoints = self.flight, len(self.flight.points)
        sta, tp1, tp2, tp3, end = 0, -1, -1, -1, nPoints-1
        for tp1 in range(1, nPoints-3):
            leg1 = self.distance(flight.points[sta], flight.points[tp1])
            for tp2 in range(tp1+1, nPoints-2):
                leg2 = self.distance(flight.points[tp1], flight.points[tp2])
                tp3 = tp2+1
                while tp3 < nPoints-1:
                    leg3 = self.distance(flight.points[tp2], flight.points[tp3])
                    distance = leg1 + leg2 + leg3 + self.distance(flight.points[tp3], flight.points[end])
                    if distance > circuit["distance"]:
                        circuit = {"sta": sta, "tps": [tp1, tp2, tp3], "end": end, "distance": distance}
                        print circuit
                        tp3 += 1
                    else:
                        tp3 = self.forward(tp3, 0.5 *(circuit["distance"] - distance))
        return circuit
    
class FlightExporter(FlightBase):

    def __init__(self, flight):
        self.flight = flight

    def toText(self):
        text = """
        Date: %s\tPilot: %s
        Registration: %s\tType: %s\t\tClass: %s
        Points: %d
        """ % (self.flight.metadata["dte"].strftime("%Y-%m-%d"), 
        self.flight.metadata["plt"], self.flight.metadata["gid"],
        self.flight.metadata["gty"], self.flight.metadata["ccl"], 
        len(self.flight.points))
        kml = self.flight.pathInKml()
        print "%s :: %d" % (kml, len(kml))
        return text

    def toFusionTable(self, tableId):
        sql = """
            INSERT INTO %s (Date, Pilot, Registration, Type, Class, Points)
            VALUES ('%s', '%s', '%s', '%s', '%s', '%s')
        """ % (tableId, self.flight.metadata["dte"].strftime("%Y-%m-%d"), 
            self.flight.metadata["plt"], self.flight.metadata["gid"],
            self.flight.metadata["gty"], self.flight.metadata["ccl"],
            self.flight.pathInKml())
        return sql

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
        print FlightExporter(flightReader.flight).export()
        flightOpt = FlightOptimizer(flightReader.flight)
        circuit = flightOpt.optimize3()

if __name__ == "__main__":
    flightCmd = FlightCmdLine()
    sys.exit(flightCmd.run())
