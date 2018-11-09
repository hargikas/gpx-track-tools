import glob
import json
import math
import sys
import statistics
import os

import gpxpy
import srtm

from haversine import Haversine


def is_closer_than(current_point, reference_point, meters):
    distance = Haversine(current_point, reference_point).meters
    if distance <= meters:
        return True
    return False

def get_routes(filename):
    data = None
    with open(filename, 'r') as json_file:
        data = json.load(json_file)
    for route in data['routes']:
        print("Setting up route '%s'" % (route["name"]), end=" ")
        route['start_point'] = data['points'][route['start']]
        route['end_point'] = data['points'][route['end']]
        route['distance'] = Haversine((route['start_point']['latitude'], route['start_point']['longitude']),
                                      (route['end_point']['latitude'], route['end_point']['longitude'])).meters
        check_radius = route['distance'] * data['proximity_limits']['ratio']
        check_radius = min(check_radius, data['proximity_limits']['max'])
        check_radius = max(check_radius, data['proximity_limits']['min'])
        route['check_radius'] = check_radius
        print("with straight line distance of %.1fkm and a start/end check with a radius of %.1fm" % (route['distance']/1000.0, route['check_radius']))
    return data

def calculate_mean_offroute(route, points):
    offroute = []
    offroute_directional = []
    halfsize = len(points)/2
    for i, point in enumerate(points):
        start_distance = Haversine((route['start_point']['latitude'], route['start_point']['longitude']),
                                       (point.latitude, point.longitude)).meters
        end_distance = Haversine((point.latitude, point.longitude),
                                       (route['end_point']['latitude'], route['end_point']['longitude'])).meters
        if i < halfsize:
            offroute_directional.append(start_distance)
        else:
            offroute_directional.append(end_distance)
            
        offroute.append(start_distance + end_distance)

    off_route = math.ceil(statistics.mean(offroute) - route['distance'])
    off_direction = math.ceil(statistics.mean(offroute_directional))
    return (off_route, off_direction)
                                    

def data_in_desc(input_str, points_gpx):
    # Straight Line Distance
    straight_distance_km = 0
    if len(points_gpx) > 1:
        straight_distance_km = Haversine((points_gpx[0].latitude, points_gpx[0].longitude),
                                         (points_gpx[-1].latitude, points_gpx[-1].longitude)).km
    input_str = input_str.replace("#STRAIGHT_DISTANCE_KM#", "%.1f" % (straight_distance_km))

    # Height Difference
    height_diff = 0
    if len(points_gpx) > 1:
        height_diff = points_gpx[-1].elevation - points_gpx[0].elevation
    input_str = input_str.replace("#HEIGHT_DIFFERENCE#", "%.1f" % (height_diff))


    return input_str


def process_file(filename, routes):
    new_gpx_xml = ''
    filename = os.path.abspath(filename)

    print("Reading file:", filename)
    with open(filename, 'r') as gpx_file:
        gpx = gpxpy.parse(gpx_file)

        print("Adjusting Elevation Data")
        elevation_data = srtm.get_data()
        elevation_data.add_elevations(gpx, smooth=True)

        for track in gpx.tracks:
            print("Checking track: '%s'" % (track.name), end='... ')
            track_found = False
            flat_points = [point for segment in track.segments for point in segment.points]
            track_size = len(flat_points)
            check_size = math.ceil(track_size*routes['proximity_limits']['ratio'])
            start_points = flat_points[:check_size]
            end_points = flat_points[:-check_size]
            best_offroute = ()
            
            for i, route in enumerate(routes['routes']):
                check_start = False
                for point in start_points:
                    if is_closer_than((point.latitude, point.longitude),
                                      (route['start_point']['latitude'], route['start_point']['longitude']),
                                      route['check_radius']):
                        check_start = True
                        break
                
                check_end = False
                for point in end_points:
                    if is_closer_than((point.latitude, point.longitude),
                                      (route['end_point']['latitude'], route['end_point']['longitude']),
                                      route['check_radius']):
                        check_end = True
                        break

                if check_start and check_end:
                    track_found = True
                    track.name = route['name']
                    track.description = data_in_desc(route['description'], flat_points)
                    break
                
                # Failed to a good start or ending point
                if route['approximate']:
                    off_route, off_dir = calculate_mean_offroute(route, flat_points)
                    if best_offroute:
                        if off_route < best_offroute[1]:
                            best_offroute = (i, off_route, off_dir)
                        elif off_route == best_offroute[1] and off_dir < best_offroute[2]:
                            best_offroute = (i, off_route, off_dir)
                    else:
                        best_offroute = (i, off_route, off_dir)
            
            if track_found:
                print('Route found and renamed to: %s' % (track.name))
            else:
                if best_offroute and best_offroute[1] < routes['proximity_limits']['offroute-limit']:
                    route_name = routes['routes'][best_offroute[0]]['name'] + \
                                 ' (off-route: %dm)' % (best_offroute[1])
                    route_desc = routes['routes'][best_offroute[0]]['description']
                    print('Approximate route found: %s' % (route_name))
                    track.name = route_name
                    track.description = data_in_desc(route_desc, flat_points)
                else:
                    print('Route not found.')
                    track.description = "Unknown route with id: " + track.name
                    track.name = "Unkown Route"
        
        new_gpx_xml = gpx.to_xml()


    directory = os.path.dirname(filename)
    new_directory = os.path.join(directory, 'fixed')
    os.makedirs(new_directory, exist_ok=True)

    new_filename = os.path.join(new_directory, os.path.basename(filename))
    print("Writing file:", new_filename)
    with open(new_filename, 'w') as gpx_file:
        gpx_file.write(new_gpx_xml)
        

def main():
    # Setup pre-defined routes
    routes = get_routes('routes.json')

    for arg in sys.argv[1:]:
        for filename in glob.iglob(arg):
            process_file(filename, routes)


if __name__ == '__main__':
    main()
