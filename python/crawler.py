import logging

from google.appengine.api.taskqueue import Task
from google.appengine.ext.webapp import RequestHandler, WSGIApplication
from google.appengine.ext.webapp.util import run_wsgi_app

from igc import FlightReader, FlightExporter, FlightFetcher

class NetcoupeHandler(RequestHandler):

    def get(self):
        logging.info("NetcoupeHandler: started")
        url = "http://netcoupe.net/Download/DownloadIGC.aspx?FileID=7347"
        task = Task(url="/crawler/netcoupe/worker", params={"url": url})
        task.add("flightprocess")

class NetcoupeWorker(RequestHandler):

    def post(self):
        url = self.request.get('url')
        logging.info("NetcoupeWorker: processing flight :: url=%s" % url)
        logging.debug("NetcoupeWorker: fetching flight :: url=%s" % url)
        reader = FlightReader( FlightFetcher(url).fetch() )
        exporter = FlightExporter(reader.flight)
        logging.debug(exporter.toFusionTable(111))

def main():
    app = WSGIApplication([
            ('/crawler/netcoupe', NetcoupeHandler),
            ('/crawler/netcoupe/worker', NetcoupeWorker),
            ], debug=True)
    logging.getLogger().setLevel(logging.DEBUG)
    run_wsgi_app(app)

if __name__ == '__main__':
    main()
