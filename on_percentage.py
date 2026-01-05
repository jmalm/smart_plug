import appdaemon.plugins.hass.hassapi as hass
import datetime


class OnByPercentage(hass.Hass):
    """
    Turn on a device a given percentage of the time, when the electricity price is the lowest, or always,
    when the electricity price is below a given threshold.

    Args:
        device_entity_id: The entity ID of the device to control.
        percentage: (Optional) Initial percentage value (0-100). Defaults to 50. Can be overridden by percentage_entity_id.
        price_entity_id: The entity ID of the electricity price sensor.
        price_threshold: Price threshold below which the device is always on.
        schedule_entity_id: Entity ID for the schedule visualization.
        percentage_entity_id: (Optional) Entity ID of an input_number for dynamic percentage control.
    """
    percentage = 50
    price_entity_id = None
    price_threshold = 0.0
    device = None
    schedule_entity_id = None
    percentage_entity_id = None

    def initialize(self):
        device_entity_id = str(self.args['device_entity_id'])
        self.device = self.get_entity(device_entity_id)
        self.percentage = int(self.args.get('percentage', 50))
        self.price_entity_id = str(self.args['price_entity_id'])
        self.price_threshold = float(self.args['price_threshold'])
        self.schedule_entity_id = str(self.args['schedule_entity_id'])
        self.percentage_entity_id = self.args.get('percentage_entity_id')

        if self.percentage_entity_id:
            self.listen_state(self.percentage_changed, self.percentage_entity_id)
            current_percentage = self.get_state(self.percentage_entity_id)
            if current_percentage is not None:
                self.percentage = int(float(current_percentage))
            else:
                # Set initial value if entity exists but no state
                self.set_state(self.percentage_entity_id, state=self.percentage)

        self.run_hourly(self.set_suitable_state, datetime.time(0, 1, 0))
        self.set_suitable_state()

    def percentage_changed(self, entity, attribute, old, new, kwargs):
        if new is not None:
            self.percentage = int(float(new))
            self.log(f"Percentage updated to {self.percentage}")
            # Optionally, re-evaluate the state immediately
            self.set_suitable_state()

    def set_suitable_state(self, *args, **kwargs):
        state = self.get_state(self.price_entity_id, attribute="all")
        current_price = float(state['state'])
        tomorrow = state.get("attributes", {}).get("raw_tomorrow", [])
        today = state.get("attributes", {}).get("raw_today", [])
        currency = str(state.get("attributes", {}).get("currency"))
        possible_hours = today + tomorrow
        prices = [float(h['value']) for h in possible_hours]

        # Should switch be on or off?
        on, reason = self.should_be_on(current_price, prices)
        target_state = 'on' if on else 'off'

        # Create the schedule (for visualization).
        should_be_on_hours = [h for h in possible_hours if self.should_be_on(h['value'], prices)[0]]
        schedule = get_contiguous_slots(should_be_on_hours)
        self.log(f"Schedule: {schedule}")
        self.set_state(self.schedule_entity_id, state=target_state, attributes={"schedule": schedule}, replace=True)

        # Turn on or off, when needed.
        change_state = self.device.state != target_state
        log_level = "INFO" if change_state else "DEBUG"
        message = f"Electricity price is {current_price} {currency}/kWh which is {reason}."
        if change_state:
            message += f" Turning {self.device.friendly_name} {target_state}."
            if target_state == 'on':
                self.turn_on(self.device.entity_id)
            else:
                self.turn_off(self.device.entity_id)
        else:
            message += f" {self.device.friendly_name} is already {target_state}."
        self.log(message, level=log_level)

    def should_be_on(self, price, prices):
        if price <= self.price_threshold:
            return True, f"lower than threshold ({self.price_threshold})"
        if price_is_among_lowest(price, prices, self.percentage):
            return True, f"among the lowest {self.percentage} % of the hourly prices"
        return False, f"NOT among the lowest {self.percentage} % of the hourly prices"


def get_contiguous_slots(slots: list[dict[str, datetime]]) -> list[dict[str, datetime]]:
    """Get the contiguous slots of the given prices."""
    sorted_slots = sorted(slots, key=lambda x: x['start'])

    def start_end(s: dict[str, datetime]) -> dict[str, datetime]:
        return {'start': s['start'], 'end': s['end']}

    contiguous_slots = []
    for slot in sorted_slots:
        if len(contiguous_slots) == 0:
            contiguous_slots.append(start_end(slot))
        elif contiguous_slots[-1]['end'] == slot['start']:
            contiguous_slots[-1]['end'] = slot['end']
        else:
            contiguous_slots.append(start_end(slot))
    return contiguous_slots


def price_is_among_lowest(current_price: float, prices: list[float], percentage: float) -> bool:
    """
    Return true when *current_price* is within the *percentage* % lowest *prices*.
    False otherwise.

    Example:

    >>> price_is_among_lowest(2, [1, 2, 3, 4, 5], 0.4)
    True
    >>> price_is_among_lowest(4, [1, 2, 3, 4, 5], 0.4)
    False

    """
    from bisect import bisect
    index = bisect(sorted(prices), current_price)
    return index / len(prices) <= percentage / 100
