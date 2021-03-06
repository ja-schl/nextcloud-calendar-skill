"""
The software class that handles connection to and requests from the Nextcloud calendar
"""
from datetime import datetime
import datetime as dt

import caldav
import icalendar
import pytz

Utc = pytz.UTC


class CalDavInterface:
    """
    Interface to connect to a Nextcloud calendar using the CalDav protocol
    """

    def __init__(self, url, username, password, local_timezone):
        self.local_timezone = local_timezone
        self.client = caldav.DAVClient(
            url=url,
            username=username,
            password=password
        )
        self.calendar = self.get_calendar()

    def get_calendar(self):
        """
        Get calendar for existing Nextcloud calendar
        :return: calendar instance
        """
        my_principal = self.client.principal()
        return my_principal.calendars()[0]


    def get_event_details(self, event):
        """
        Parses ical strings for event to dictionary containing title, start time and end time
        :param event: ical string of event
        :return: dictionary representation of event
        """
        start = None
        if "DTSTART" in event.keys():
            start = event["DTSTART"].dt
            if not isinstance(start, datetime):
                start = datetime.combine(start, datetime.min.time())
                start = start.replace(tzinfo=Utc)
            else:
                start = start.astimezone(self.local_timezone)
        end = None
        if "DTEND" in event.keys():
            end = event["DTEND"].dt
            if not isinstance(end, datetime):
                end = datetime.combine(end, datetime.min.time())
                end = end.replace(tzinfo=Utc)
            else:
                end = end.astimezone(self.local_timezone)
        title = "untitled event"
        if "SUMMARY" in event.keys():
            title = str(event["SUMMARY"])

        return {"title": title, "starttime": start, "endtime": end}

    def parse_ics_events(self, events):
        """
        Parses calendar events from ical format to python dictionary
        :param events: list of events (ical strings) that should be parsed
        :return: python list containing the pared events as dictionaries
        """
        parsed_events = []
        for event in events:
            cal = icalendar.Calendar.from_ical(event.data, True)
            url = event.url
            for vevent in cal[0].walk("vevent"):
                event_details = self.get_event_details(vevent)
                event_details["event_url"] = url
                parsed_events.append(event_details)
        return parsed_events

    def get_events_for_timeperiod(self, startdate, enddate):
        """
        Returns list of parsed events in a specific time period
        :param startdate: start date of search period
        :param enddate: end date of search period
        :return: list of parsed events (python dicts)
        """
        events = self.calendar.date_search(start=startdate, end=enddate, expand=True)
        return self.parse_ics_events(events)

    def get_events_for_date(self, requested_date):
        """
        Returns list of parsed events for a specific date
        :param requested_date: date of the request
        :return: list of parsed events (python dict)
        """
        return self.get_events_for_timeperiod(
            datetime.combine(requested_date, datetime.min.time()),
            datetime.combine(requested_date, datetime.max.time())
        )

    def get_next_event(self):
        """
        Returns next event planned in the calendar.
        :return: next event as python dictionary. If there is no event planned in the future
        "None" is returned
        """
        all_events = self.calendar.events()
        parsed_events = self.parse_ics_events(all_events)
        sorted_events = sorted(parsed_events, key=lambda i: i["starttime"])
        for event in sorted_events:
            starttime = event["starttime"]
            now = datetime.today()
            current_time = now.replace(tzinfo=starttime.tzinfo)
            if starttime > current_time:
                return event
        return None

    def get_events_with_title(self, title):
        """
        Get all events from the calendar, parse it to python dict representation
        and filter them into a list only events matching the given title.
        :param title: string that the event summary needs to contain
        :return: list of matching events in python dictionary representation
        """
        all_events = self.calendar.events()
        parsed_events = self.parse_ics_events(all_events)
        matching_events = [event for event in parsed_events
                           if title.lower() in event["title"].lower()]
        return matching_events

    def create_new_event(self, title, date, duration, fullday):
        """
        Creates a new event in the Nextcloud calendar with the given details.
        :param title: title used in summary of the new event
        :param date: datetime used as dtstart of the event
        :param duration: duration to calculate the dtend of the event
        :param fullday: boolean that indicates if the event is a full-day event
        """
        cal = icalendar.Calendar()
        event = icalendar.Event()
        event.add("summary", title)

        if fullday:
            start = date.date()
            end = (date + dt.timedelta(duration)).date()
            date = start
        else:
            end = date + duration

        event.add("dtstart", date)
        event.add("dtend", end)

        cal.add_component(event)
        self.calendar.add_event(cal)

    def delete_event(self, event):
        """
        Gets a CalDav event object from the event url and delete
        the event form the calendar.
        :param event: event in python dict representation
        """
        caldav_event = self.calendar.event_by_url(event["event_url"])
        caldav_event.delete()

    def rename_event(self, event, new_title):
        """
        Changes the summary field of a given event to a new title.
        :param event: the event in python dict representation
        :param new_title: the desired new title of the event
        """
        caldav_event = self.calendar.event_by_url(event["event_url"])
        caldav_event.vobject_instance.vevent.summary.value = new_title
        caldav_event.save()
