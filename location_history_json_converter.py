#!/usr/bin/env python

# Copyright 2012-2017 Gerwin Sturm
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import division

import sys
import json
import math
from argparse import ArgumentParser, ArgumentTypeError
from datetime import datetime
import logging
from shapely.geometry import Polygon
from shapely.geometry import Point


def valid_polygon(s):
    try:
        [lat, lon] = s.split(",")
        return float(lat), float(lon)
    except ValueError:
        msg = "Not a valid point: '{0}'.".format(s)
        raise ArgumentTypeError(msg)


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise ArgumentTypeError(msg)


def check_point(polygon, lon, lat):
    # build a shapely point from your geopoint
    point = Point(lon / 10000000, lat / 10000000)
    # the contains function does exactly what you want
    return polygon.contains(point)


def dateCheck(timestampms, startdate, enddate):
    dt = datetime.fromtimestamp(int(timestampms) / 1000)
    if startdate and startdate > dt: return False
    if enddate and enddate < dt: return False
    return True


def main():
    arg_parser = ArgumentParser()
    arg_parser.add_argument("input", help="Input File (JSON)")
    arg_parser.add_argument("-o", "--output", help="Output File (will be overwritten!)")
    arg_parser.add_argument("-f", "--format", choices=["kml", "json", "csv", "js", "gpx", "gpxtracks"], default="kml",
                            help="Format of the output")
    arg_parser.add_argument("-v", "--variable", default="locationJsonData",
                            help="Variable name to be used for js output")
    arg_parser.add_argument('-s', "--startdate", help="The Start Date - format YYYY-MM-DD (0h00)", type=valid_date)
    arg_parser.add_argument('-e', "--enddate", help="The End Date - format YYYY-MM-DD (0h00)", type=valid_date)
    arg_parser.add_argument('-c', "--chronological", help="Sort items in chronological order", action="store_true")
    arg_parser.add_argument('-p', "--polygon",
                            help="Enter a list of points (lat,lon) that create a polygon. If 2 points are given (bottomleft, upper right) a rectangular is created",
                            metavar="lat,lon", nargs='*', type=valid_polygon)
    args = arg_parser.parse_args()

    if not args.output:  # if the output file is not specified, set to input filename with a diffrent extension
        args.output = '.'.join(args.input.split('.')[:-1]) + '.' + args.format

    if args.input == args.output:
        arg_parser.error("Input and output have to be different files")
        return

    if args.polygon and len(args.polygon) < 2:
        arg_parser.error("Polygon needs at least 2 points to create a rectangule (bottom left and top right)")
        return

    try:
        json_data = open(args.input).read()
    except:
        print("Error opening input file")
        return

    try:
        data = json.loads(json_data)
    except:
        print("Error decoding json")
        return

    if "locations" in data and len(data["locations"]) > 0:
        try:
            f_out = open(args.output, "w")
        except:
            print("Error creating output file for writing")
            return

        items = data["locations"]

        if args.startdate or args.enddate:
            items = [item for item in items if dateCheck(item["timestampMs"], args.startdate, args.enddate)]

        if args.chronological:
            items = sorted(items, key=lambda item: item["timestampMs"])

        if args.polygon:

            if len(args.polygon) == 2:
                # create a Rectangul
                [bottom_lx, top_rx] = args.polygon
                [bottom_lx_lat, bottom_lx_lon] = bottom_lx
                [top_rx_lat, top_rx_lon] = top_rx
                ext = [(float(bottom_lx_lat), float(bottom_lx_lon)), (float(bottom_lx_lat), float(top_rx_lon)),
                       (float(top_rx_lat), float(top_rx_lon)), (float(top_rx_lat), float(bottom_lx_lon))]

            else:
                ext = [(elem.split(",")[0], elem.split(",")[1]) for elem in args.polygon]

            print("Polygon created: {}".format(ext))
            polygon = Polygon(ext)
            items = [item for item in items if check_point(polygon, item["latitudeE7"], item["longitudeE7"])]

        if args.format == "json" or args.format == "js":
            if args.format == "js":
                f_out.write("window.%s = " % args.variable)

            f_out.write("{\"locations\":[")
            first = True

            for item in items:
                if first:
                    first = False
                else:
                    f_out.write(",")
                f_out.write("{")
                f_out.write("\"timestampMs\":%s," % item["timestampMs"])
                f_out.write("\"latitudeE7\":%s," % item["latitudeE7"])
                f_out.write("\"longitudeE7\":%s" % item["longitudeE7"])
                f_out.write("}")
            f_out.write("]}")
            if args.format == "js":
                f_out.write(";")

        if args.format == "csv":
            f_out.write("Time,Latitude,Longitude\n")
            for item in items:
                f_out.write(datetime.fromtimestamp(int(item["timestampMs"]) / 1000).strftime("%Y-%m-%d %H:%M:%S"))
                f_out.write(",")
                f_out.write("%s,%s\n" % (item["latitudeE7"] / 10000000, item["longitudeE7"] / 10000000))

        if args.format == "kml":
            f_out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            f_out.write("<kml xmlns=\"http://www.opengis.net/kml/2.2\">\n")
            f_out.write("  <Document>\n")
            f_out.write("    <name>Location History</name>\n")
            for item in items:
                f_out.write("    <Placemark>\n")
                # Order of these tags is important to make valid KML: TimeStamp, ExtendedData, then Point
                f_out.write("      <TimeStamp><when>")
                f_out.write(datetime.fromtimestamp(int(item["timestampMs"]) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ"))
                f_out.write("</when></TimeStamp>\n")
                if "accuracy" in item or "speed" in item or "altitude" in item:
                    f_out.write("      <ExtendedData>\n")
                    if "accuracy" in item:
                        f_out.write("        <Data name=\"accuracy\">\n")
                        f_out.write("          <value>%d</value>\n" % item["accuracy"])
                        f_out.write("        </Data>\n")
                    if "speed" in item:
                        f_out.write("        <Data name=\"speed\">\n")
                        f_out.write("          <value>%d</value>\n" % item["speed"])
                        f_out.write("        </Data>\n")
                    if "altitude" in item:
                        f_out.write("        <Data name=\"altitude\">\n")
                        f_out.write("          <value>%d</value>\n" % item["altitude"])
                        f_out.write("        </Data>\n")
                    f_out.write("      </ExtendedData>\n")
                f_out.write("      <Point><coordinates>%s,%s</coordinates></Point>\n" % (
                    item["longitudeE7"] / 10000000, item["latitudeE7"] / 10000000))
                f_out.write("    </Placemark>\n")
            f_out.write("  </Document>\n</kml>\n")

        if args.format == "gpx" or args.format == "gpxtracks":
            f_out.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
            f_out.write(
                "<gpx xmlns=\"http://www.topografix.com/GPX/1/1\" version=\"1.1\" creator=\"Google Latitude JSON Converter\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd\">\n")
            f_out.write("  <metadata>\n")
            f_out.write("    <name>Location History</name>\n")
            f_out.write("  </metadata>\n")
            if args.format == "gpx":
                for item in items:
                    f_out.write("  <wpt lat=\"%s\" lon=\"%s\">\n" % (
                        item["latitudeE7"] / 10000000, item["longitudeE7"] / 10000000))
                    if "altitude" in item:
                        f_out.write("    <ele>%d</ele>\n" % item["altitude"])
                    f_out.write("    <time>%s</time>\n" % str(
                        datetime.fromtimestamp(int(item["timestampMs"]) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")))
                    f_out.write("    <desc>%s" % datetime.fromtimestamp(int(item["timestampMs"]) / 1000).strftime(
                        "%Y-%m-%d %H:%M:%S"))
                    if "accuracy" in item or "speed" in item:
                        f_out.write(" (")
                        if "accuracy" in item:
                            f_out.write("Accuracy: %d" % item["accuracy"])
                        if "accuracy" in item and "speed" in item:
                            f_out.write(", ")
                        if "speed" in item:
                            f_out.write("Speed:%d" % item["speed"])
                        f_out.write(")")
                    f_out.write("</desc>\n")
                    f_out.write("  </wpt>\n")
            if args.format == "gpxtracks":
                f_out.write("  <trk>\n")
                f_out.write("    <trkseg>\n")
                lastloc = None
                # The deltas below assume input is in chronological or reverse chronological order.
                # If it's not, use the '--chronological' option or uncomment this:
                # items = sorted(data["data"]["items"], key=lambda x: x['timestampMs'], reverse=True)
                for item in items:
                    if lastloc:
                        timedelta = abs((int(item['timestampMs']) - int(lastloc['timestampMs'])) / 1000 / 60)
                        distancedelta = getDistanceFromLatLonInKm(item['latitudeE7'] / 10000000,
                                                                  item['longitudeE7'] / 10000000,
                                                                  lastloc['latitudeE7'] / 10000000,
                                                                  lastloc['longitudeE7'] / 10000000)
                        if timedelta > 10 or distancedelta > 40:
                            # No points for 10 minutes or 40km in under 10m? Start a new track.
                            f_out.write("    </trkseg>\n")
                            f_out.write("  </trk>\n")
                            f_out.write("  <trk>\n")
                            f_out.write("    <trkseg>\n")
                    f_out.write("      <trkpt lat=\"%s\" lon=\"%s\">\n" % (
                        item["latitudeE7"] / 10000000, item["longitudeE7"] / 10000000))
                    if "altitude" in item:
                        f_out.write("        <ele>%d</ele>\n" % item["altitude"])
                    f_out.write("        <time>%s</time>\n" % str(
                        datetime.fromtimestamp(int(item["timestampMs"]) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")))
                    if "accuracy" in item or "speed" in item:
                        f_out.write("        <desc>\n")
                        if "accuracy" in item:
                            f_out.write("          Accuracy: %d\n" % item["accuracy"])
                        if "speed" in item:
                            f_out.write("          Speed:%d\n" % item["speed"])
                        f_out.write("        </desc>\n")
                    f_out.write("      </trkpt>\n")
                    lastloc = item
                f_out.write("    </trkseg>\n")
                f_out.write("  </trk>\n")
            f_out.write("</gpx>\n")

        f_out.close()

    else:
        print("No data found in json")
        return


# Haversine formula
def getDistanceFromLatLonInKm(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the earth in km
    dlat = deg2rad(lat2 - lat1)
    dlon = deg2rad(lon2 - lon1)
    a = math.sin(dlat / 2) * math.sin(dlat / 2) + \
        math.cos(deg2rad(lat1)) * math.cos(deg2rad(lat2)) * \
        math.sin(dlon / 2) * math.sin(dlon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = R * c  # Distance in km
    return d


def deg2rad(deg):
    return deg * (math.pi / 180)


if __name__ == "__main__":
    sys.exit(main())
