from mapbox import MapMatcher
import gpxpy
import gpxpy.gpx
import srtm

import os
import time
import datetime

LIMIT_JSON = 100

def roundSeconds(dateTimeObject):
    newDateTime = dateTimeObject

    if newDateTime.microsecond >= 500000:
        newDateTime = newDateTime + datetime.timedelta(seconds=1)

    return newDateTime.replace(microsecond=0)

def unique_list(seq):
    seen = set()
    seen_add = seen.add
    return [tuple(x) for x in seq if not (tuple(x) in seen or seen_add(tuple(x)))]

def gpx_points_to_GeoJSONs(points):
    json_all = []
    json_cur = {}
    for i, point in enumerate(points):
        if (i % LIMIT_JSON == 0):
            if json_cur:
                json_all.append(json_cur)
            json_cur = {
                "type": "Feature",
                "properties": {
                    "coordTimes": []},
                "geometry": {
                    "type": "LineString",
                    "coordinates": []}}

        # Add points
        timestamp_cur = point.time.strftime('%Y-%m-%dT%H:%M:%SZ')
        #point_cur = [point.latitude, point.longitude]
        point_cur = [point.longitude, point.latitude]
        json_cur["properties"]["coordTimes"].append(timestamp_cur)
        json_cur["geometry"]["coordinates"].append(point_cur)
    json_all.append(json_cur)
    return json_all

def GeoJSONs_to_new_gpx(input_jsons, flat_points, new_gpx):
    # Map Matrching response has the coordinates, matches and indeces with the input
    flat_coord = [coord for json_res in input_jsons for feature in json_res['features'] for coord in feature['geometry']['coordinates']]
    flat_matches = [coord for json_res in input_jsons for feature in json_res['features'] for coord in feature['properties']['matchedPoints']]
    flat_indeces = [index for json_res in input_jsons for feature in json_res['features'] for index in feature['properties']['indices']]

    # Fix Indeces (It is broken with the limit)
    prev_index = -1
    for i in range(len(flat_indeces)):
        while prev_index > flat_indeces[i]:
            flat_indeces[i] += LIMIT_JSON
        prev_index = flat_indeces[i]

    # Insert GPX time
    last_index = 0
    for i, e in enumerate(flat_indeces):
        cur_time = flat_points[e].time
        last_index = flat_coord.index(flat_matches[i], last_index)
        if last_index != -1:
            flat_coord[last_index].append(cur_time)
    
    # Fix empty times
    prev_time = None
    next_time = None
    for i in range(len(flat_coord)):
        if len(flat_coord[i]) == 3:
            prev_time = flat_coord[i][2]
        else:
            # Find next specified time and how many empties there are
            none_time = 0
            for j in range(i, len(flat_coord)):
                if len(flat_coord[j]) == 3:
                    next_time = flat_coord[j][2]
                    break
                else:
                    none_time +=1

            # Calculate the time_intervals
            time_diff = (next_time - prev_time).total_seconds() / (none_time + 1)
            prev_time = prev_time + datetime.timedelta(seconds=time_diff)
            flat_coord[i].append(roundSeconds(prev_time))

    flat_coord = unique_list(flat_coord)
    return flat_coord


def snap_roads(input_json):
    # Create a limit to how many call per minute are permited
    if input_json and input_json["geometry"]["coordinates"]:
        print("Calling the Map-Matching Web Service for %d points" % (len(input_json["geometry"]["coordinates"])))
        time.sleep(1)
        service = MapMatcher(
            access_token='pk.eyJ1IjoiaGFyZ2lrYXMiLCJhIjoiY2pvOWx6b3RnMWl1ejNwczExdGhwOWhuOCJ9.4o3i_BYb63hnZr8Licb0AgXXX')
        response = service.match(input_json, profile='mapbox.cycling')
        if response.status_code == 200:
            response_GeoJSON = response.geojson()
            return response_GeoJSON
        else:
            print("HTTP ERROR:", response.status_code)
    return None


def process_file(filename):
    filename = os.path.abspath(filename)

    # Creating a new file:
    new_gpx = gpxpy.gpx.GPX()

    print("Reading file:", filename)
    with open(filename, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)

        if gpx.name:
            new_gpx.name = gpx.name
        
        if gpx.description:
            new_gpx.description = gpx.description

        for track in gpx.tracks:
            print("Checking track: '%s'" % (track.name))
            flat_points = [
                point for segment in track.segments for point in segment.points]
            # Break points into many GeoJSON (due to point limit), and call the map-matching web-service
            json_fixed = [snap_roads(json_cur) for json_cur in gpx_points_to_GeoJSONs(flat_points)]
            
            everything_ok = True
            for json_cur in json_fixed:
                if (not json_cur['code']) or (json_cur['code'] != 'Ok'):
                    everything_ok = False
            
            if everything_ok:
                flat_coord = GeoJSONs_to_new_gpx(json_fixed, flat_points, new_gpx)

                # Create track in our GPX:
                gpx_track = gpxpy.gpx.GPXTrack()
                if track.name:
                    gpx_track.name = track.name
                if track.description:
                    gpx_track.description = track.description
                new_gpx.tracks.append(gpx_track)

                # Create segments in our GPX track:
                gpx_segment = gpxpy.gpx.GPXTrackSegment()
                gpx_track.segments.append(gpx_segment)

                # Create points:
                for longitude, latitude, cur_time in flat_coord:
                    gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude, longitude, elevation=0, time=cur_time))


    print("Adjusting Elevation Data")
    elevation_data = srtm.get_data()
    elevation_data.add_elevations(new_gpx, smooth=True)

    directory = os.path.dirname(filename)
    new_directory = os.path.join(directory, 'fixed')
    os.makedirs(new_directory, exist_ok=True)

    new_filename = os.path.join(new_directory, os.path.basename(filename))
    print("Writing file:", new_filename)
    with open(new_filename, 'w') as gpx_file:
        gpx_file.write(new_gpx.to_xml())


if __name__ == '__main__':
    process_file("D:\\tmp\\ridewithgps\\20181109-082114(1).gpx")
    # snap_roads()
