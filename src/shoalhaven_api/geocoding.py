import requests
from shoalhaven_api.location import Location
from os import getenv
from dotenv import load_dotenv

load_dotenv()


def geocodeLocationString(query: str) -> Location:
    # Fetch with MapBox API
    api = f"https://api.mapbox.com/search/geocode/v6/forward?q={query}&country=au&access_token={getenv('MAPBOX_API')}"
    response = requests.get(api)

    try:
        # Pull the data we want, assume first result is correct
        properties = response.json()["features"][0]["properties"]
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
    except KeyError:
        print(f"Could not find address: '{query}'")
        location = Location(query, "", "", "", "", "", (0, 0))

    return location
