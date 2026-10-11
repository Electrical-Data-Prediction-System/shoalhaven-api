from os import getenv

import requests
from dotenv import load_dotenv

from shoalhaven_api.location import Location

load_dotenv()


def geocodeLocationString(query: str) -> Location:
    # Fetch with MapBox API
    response = requests.get(
        "https://api.mapbox.com/search/geocode/v6/forward?",
        params={"q": query, "country": "au", "access_token": getenv("MAPBOX_API")},
        timeout=10,
    )

    try:
        if response.status_code == 200:
            # Pull the data we want, assume first result is correct
            properties = response.json()["features"][0]["properties"]

            if len(properties) <= 0:
                print(f"Could not find address: '{query}'")
                return Location(query, "", "", "", "", "", (0, 0))

            context = properties["context"]

            # Format into our Location class
            location = Location(
                properties["full_address"],
                context["street"]["name"],
                context["postcode"]["name"],
                context["place"]["name"],
                context["region"]["name"],
                context["country"]["name"],
                (
                    float(properties["coordinates"]["longitude"]),
                    float(properties["coordinates"]["latitude"]),
                ),
            )
        else:
            # Invalid response, default to fallback
            print("Invalid response from MapBox API")
            location = Location(query, "", "", "", "", "", (0, 0))
    except (KeyError, IndexError, requests.RequestException) as e:
        print(f"Could not find address: '{query}':\n{e}")
        location = Location(query, "", "", "", "", "", (0, 0))

    return location
