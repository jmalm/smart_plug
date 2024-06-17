import appdaemon.plugins.hass.hassapi as hass
import datetime


class OnByPercentage(hass.Hass):
    """
    Turn on a device a given percentage of the time, when the electricity price is the lowest, or always,
    when the electricity price is below a given threshold.
    """
    def initialize(self):
        self.device_entity_id = str(self.args['device_entity_id'])
        self.percentage = int(self.args['percentage'])
        self.price_entity_id = str(self.args['price_entity_id'])
        self.price_threshold = float(self.args['price_threshold'])
        self.device = self.get_entity(self.device_entity_id)

        self.run_hourly(self.set_suitable_state, datetime.time(0, 1, 0))
        self.set_suitable_state()

    def set_suitable_state(self, *args, **kwargs):
        state = self.get_state(self.price_entity_id, attribute="all")
        current_price = float(state['state'])
        tomorrow = state.get("attributes", {}).get("raw_tomorrow", [])
        today = state.get("attributes", {}).get("raw_today", [])
        currency = str(state.get("attributes", {}).get("currency"))
        possible_hours = today + tomorrow
        prices = [float(h['value']) for h in possible_hours]

        if current_price <= self.price_threshold or price_is_among_lowest(current_price, prices, self.percentage):
            if self.device.state == "off":
                self.log(f"Electricity price is {current_price} {currency}/kWh which is among the lowest {self.percentage} % of the hourly prices. Turning {self.device.friendly_name} on.")
                self.turn_on(self.device_entity_id)
        else:
            if self.device.state == "on":
                self.log(f"Electricity price is {current_price} {currency}/kWh which is NOT among the lowest {self.percentage} % of the hourly prices. Turning {self.device.friendly_name} off.")
                self.turn_off(self.device_entity_id)


def price_is_among_lowest(current_price : float, prices : list[float], limit : float) -> bool:
    """
    Return true when *current_price* is within the *limit* % lowest *prices*.
    False otherwise.

    Example:

    >>> price_is_among_lowest(2, [1, 2, 3, 4, 5], 0.4)
    True
    >>> price_is_among_lowest(4, [1, 2, 3, 4, 5], 0.4)
    False

    """
    from bisect import bisect
    index = bisect(sorted(prices), current_price)
    return index / len(prices) <= limit / 100
