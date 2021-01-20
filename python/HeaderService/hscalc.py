# This file is part of HeaderService
#
# Developed for the LSST Data Management System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This module contains the function used by the HeaderService to computed the
metadata not provided as SAL/DDS Telemetry/Event

"""

from astropy.time import Time
import astropy.units as u
from astropy.coordinates import AltAz, ICRS, EarthLocation
import logging

LOGGER = logging.getLogger(__name__)


def get_date(timeStamp=None, format='unix', scale='utc'):

    """
    A simple function to the get an astropy.datetime.Time object

    Parameters
    ----------

    timeStamp : float
        Optional timestamp (in seconds) passed as an argument. If None
        is received, then the function will get the time now()

    fomat: string
        Optional format (i.e.: unix) to pass to the astropy.Time function

    scale: string
        Optional scale (i.e: utc, tai) to pass to the astropy.Time function

    Returns
    -------

    t: type of astropy.datetime.Time object
       The astropy.datetime.Time object with the timeStamp requested
       in the defined scale.

    """

    if timeStamp is None:
        t = Time.now()
    else:
        t = Time(timeStamp, format=format, scale=scale)
    return t


def get_radec_from_altaz(alt, az, obstime, lat=-30.244639, lon=-70.749417, height=2663.0):

    """
    Get the ra, dec fron the altitude/azimuth and the telescope location
    using the  astropy AltAz function

    Parameters
    ----------

    alt : float
        The Altitude (angle) for the object
    az : float
        The Azimuth (angle) for the object
    obstime: float
        The time of the observation
    lat: float
        Optional, the geographic latitude in degrees
    lon: float
        Optional, the geographic longitude in degrees
    height: float
        Optional, the height in meters

    Returns
    -------

    ra: float
       The Right Ascension
    dec: float


    """

    # Get an astropy location object, using the appropiate astropy units
    location = EarthLocation.from_geodetic(lon*u.deg, lat*u.deg, height*u.m)
    # Get an astropy coordinate of frame in the Altitude-Azimuth system
    elaz = AltAz(alt=alt*u.deg, az=az*u.deg, obstime=obstime, location=location)
    coords = elaz.transform_to(ICRS)
    return coords.ra.deg, coords.dec.deg


if __name__ == "__main__":
    ra, dec = get_radec_from_altaz(alt=30, az=30, obstime=Time.now())
    print(ra, dec)
