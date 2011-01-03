window.opensoaring = window.opensoaring || {};
opensoaring.igc = opensoaring.igc || {
/**
  * Flight object.
  */
Flight: function(url, autoload) {
    this.url = url;
    this.raw = null;
    this.data = null;

    this.load = function() {
        opensoaring.igc.Util.loadFlight(this);
    }

    this.toString = function() {
        return JSON.stringify(this.data, null, 4);
    }

    if (autoload) this.load();
},

/**
  * FlightData object.
  */
FlightData: function() {
    this.manufacturer = null;
    this.header = { "FXA": null, "DTE": null, "PLT": null, "CM2": null, "GTY": null, "GID": null, 
                    "DTM": null, "RFW": null, "RHW": null, "FTY": null, "GPS": null, "PRS": null,
                    "CID": null, "CCL": null };
    this.points = [];

    this.toString = function() {
        return JSON.stringify(this);
    }
},

GFlight: function(aFlight) {
    flight = aFlight;
    polyline = null;
    polyoptions = {strokeColor: "#FF0000", strokeOpacity: 0.6, strokeWeight: 3};
    bounds = null;
    chartData = null;
    marker = null;

    this.getPolyline = function() {
        if (polyline == null) {
            var path = [];
            bounds = new google.maps.LatLngBounds();
            for (n in flight.data.points) {
                var point = flight.data.points[n];
                path.push(new google.maps.LatLng(point["lat"], point["lon"]));
                bounds.extend(path[path.length-1]);
            }
            polyoptions["path"] = path;
            polyline = new google.maps.Polyline(polyoptions);
        }
        return polyline;
    }

    this.getBounds = function () {
        if (polyline == null)
            polyline = this.getPolyline();
        return bounds;
    }

    this.getChart = function() {
        if (chartData == null) {
            chartData = { "values": [], "labels": ["Time", "Altitude"] };
            for (n in flight.data.points) {
                var point = flight.data.points[n];
                chartData["values"].push([point["time"], point["galt"]]);
            }
        }
        return chartData;
    }

    this.getMarker = function() {
        if (marker == null)
            marker = new google.maps.Marker({position: this.getPolyline().getPath().getAt(0)});
        alert(marker);
        return marker;
    }

    this.setPosition = function(event, x, points, row) {
        marker.setPosition(this.getPolyline().getPath().getAt(10));
    }
},

/**
  *
  */
Parser: {
    /**
      * Parses a string containing a track in IGC format.
      *
      * Nice read:
      * http://carrier.csi.cam.ac.uk/forsterlewis/soaring/igc_file_format/igc_format_2008.html
      */
    parse: function(data) {
        var flightData = new opensoaring.igc.FlightData();
        var records = data.split("\r\n");
        for (n in records) {
            var record = records[n];
            switch (record[0]) { // Record type is stored in the first char
                case 'A':
                    flightData.manufacturer = record.substring(1, 4);
                    break;
                case 'H':
                    var type = record.substring(2, 5);
                    var value = record.substring(Math.max(5, record.indexOf(':')+1));
                    switch (type) {
                        case "DTE":
                            flightData.header["DTE"] = 
                                new Date(20+value.substring(4), (value.substring(2,4)-1), value.substring(0,2));
                            break;
                        case "FXA":
                            flightData.header["FXA"] = parseInt(value);
                        default:
                            flightData.header[type] = value;
                    }
                    break;
                case 'B':
                    flightData.points.push({
                        "time": new Date(
                            flightData.header["DTE"].getTime() + (record.substring(1,3) * 3600000) +
                            (record.substring(3,5) * 60000) + parseInt(record.substring(5,7)*1000)),
                        "lat": opensoaring.igc.Util.dms2dd(record.substring(7,15)),
                        "lon": opensoaring.igc.Util.dms2dd(record.substring(15,24)),
                        "val": record[24],
                        "palt": record.substring(25,30),
                        "galt": parseFloat(record.substring(30,35)),
                    });
                    break;
            }
        }
        return flightData;
    },
},

/**
  * Util object.
  */
Util: {
    /**
      * Loads the data of a flight from the url stored inside the object.
      */
    loadFlight: function(flight) {
        try {
            var xmlhttp = new XMLHttpRequest();
        } catch(e) {
            return;
        }
        xmlhttp.open("GET", flight.url, false);
        xmlhttp.onreadystatechange = function() {
            if (xmlhttp.readyState==4) {
                flight.raw = xmlhttp.responseText;
                flight.data = opensoaring.igc.Parser.parse(flight.raw); 
            }
        }
        xmlhttp.send(null);
    },
    /**
      * Returns the given coordinate passed in DMS format in decimal degrees.
      */
    dms2dd: function(value) {
        var cardinal = value[value.length-1];
        var dd = null; // decimal degrees
        if (cardinal == 'N' || cardinal == 'S')
            dd = (parseFloat(value.substring(0,2))) 
                + ( (parseFloat(value.substring(2,4)) + (parseFloat(value.substring(4,7)) / 1000.0)) / 60.0 );
        else
            dd = (parseFloat(value.substring(0,3)))
                + ( (parseFloat(value.substring(3,5)) + (parseFloat(value.substring(5,8)) / 1000.0)) / 60.0 );
        if (cardinal == 'S' || cardinal == 'W') 
            dd = dd * -1;
        return dd;
    },
}

};

function init() {
    var latlng = new google.maps.LatLng(-34.397, 150.644);
    var myOptions = { 
        zoom: 10,
        center: latlng,
        mapTypeControl: false,
        mapTypeControlOptions: {
            style: google.maps.MapTypeControlStyle.DEFAULT,
            mapTypeIds: [google.maps.MapTypeId.TERRAIN, "earth"],
        },
        navigationControl: true,
        navigationControlOptions: {
            style: google.maps.NavigationControlStyle.DEFAULT,
        },
        scaleControl: true,
        scaleControlOptions: {
            style: google.maps.ScaleControlStyle.DEFAULT,
        },
        scaleControl: true,
        mapTypeId: google.maps.MapTypeId.TERRAIN,
    };
    var map = new google.maps.Map(document.getElementById("mapCanvas"), myOptions);
    var flight = new opensoaring.igc.Flight("test.igc", true);
    var gflight = new opensoaring.igc.GFlight(flight);
    gflight.getPolyline().setMap(map);
    gflight.getMarker().setMap(map);
    var chartData = gflight.getChart();
    var chart = new Dygraph(document.getElementById("mapChart"), chartData["values"], 
                {
fillGraph: true, colors: ['#0000FF'], 
                strokeWidth: 1, yAxisLabelWidth: 30, axisLabelFontSize: 12, gridLineColor: "gray",
                width: "100%", height: "100%", highlightCallback: gflight.setPosition,
                });
    map.fitBounds(gflight.getBounds());
}

