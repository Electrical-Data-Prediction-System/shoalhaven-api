class Location:
    def __init__(
        self,
        _fullAddress: str,
        _street: str,
        _postcode: str,
        _place: str,
        _region: str,
        _country: str,
        _coordinates: tuple[float, float],
    ) -> None:
        self.fullAddress = _fullAddress
        self.street = _street
        self.postcode = _postcode
        self.place = _place
        self.region = _region
        self.country = _country
        self.coordinates = _coordinates

    def to_dict(self) -> dict:
        return {
            "fullAddress": self.fullAddress,
            "street": self.street,
            "postcode": self.postcode,
            "place": self.place,
            "region": self.region,
            "country": self.country,
            "coordinates": self.coordinates,
        }
