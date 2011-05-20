import logging
import urllib
import urllib2

from google.appengine.api.taskqueue import Task
from google.appengine.ext.webapp import RequestHandler, WSGIApplication
from google.appengine.ext.webapp.util import run_wsgi_app

import appdata
from igc import FlightReader, FlightExporter, FlightFetcher

class CommonHandler(RequestHandler):

    gAuthUri = "https://www.google.com/accounts/ClientLogin"

    fusionTablesUri = "http://www.google.com/fusiontables/api/query"

    def __init__(self):
        None

    def gAuth(self, username, password, service, accountType):
        authData = urllib.urlencode(
                {"Email": username, "Passwd": password, "service": service, 
                "accountType": accountType})
        authReq = urllib2.Request(self.gAuthUri, data=authData)
        authResp = urllib2.urlopen(authReq).read()
        authDict = dict(x.split("=") for x in authResp.split("\n") if x)
        return authDict["Auth"]

class NetcoupeHandler(CommonHandler):

    def get(self):
        logging.info("NetcoupeHandler: started")
        url = "http://netcoupe.net/Download/DownloadIGC.aspx?FileID=7347"
        task = Task(url="/crawler/netcoupe/worker", params={"url": url})
        task.add("flightprocess")

class NetcoupeWorker(CommonHandler):

    def __init__(self):
        self.authToken = None

    def post(self):
        url = self.request.get('url')
        logging.info("NetcoupeWorker: processing flight :: url=%s" % url)
        if self.authToken is None:
            self.authToken = self.gAuth("rocha.porto", appdata.password, "fusiontables", "HOSTED_OR_GOOGLE")
        reader = FlightReader( FlightFetcher(url).fetch() )
        exporter = FlightExporter(reader.flight)
        req = urllib2.Request(self.fusionTablesUri,
                urllib.urlencode({"sql": exporter.toFusionTable(872803)}),
                {"Authorization": "GoogleLogin auth=%s" % self.authToken,
                "Content-Type": "application/x-www-form-urlencoded"})
        resp = urllib2.urlopen(req)
        print resp

def main():
    app = WSGIApplication([
            ('/crawler/netcoupe', NetcoupeHandler),
            ('/crawler/netcoupe/worker', NetcoupeWorker),
            ], debug=True)
    logging.getLogger().setLevel(logging.DEBUG)
    run_wsgi_app(app)

if __name__ == '__main__':
    main()
