#!/usr/bin/python

# Imports ################################################################

import re, urlparse, urllib, requests, json, math, os

from datetime import datetime, timedelta
from time import mktime

from settings import *


# Functions ##############################################################

def add_average_to_weekly_set(weekly_set):
    weekly_totals = {}
    for cohort_weekly_set in weekly_set:
        for week_nb, week_players in cohort_weekly_set['data']:
            if week_nb not in weekly_totals:
                weekly_totals[week_nb] = {'sum': week_players, 'nb_cohorts': 1}
            else:
                weekly_totals[week_nb]['sum'] += week_players
                weekly_totals[week_nb]['nb_cohorts'] += 1

    weekly_averages = []
    for week_nb, week_total in weekly_totals.iteritems():
        average = round(float(week_total['sum']) / week_total['nb_cohorts'], 1)
        weekly_averages.append([week_nb, average])

    weekly_set.append({'label': 'Average', 'data': weekly_averages})
    return weekly_set


# Classes ################################################################

class TimeSliced(object):

    def __init__(self):
        # datetime objects
        self.start_date = None
        self.end_date = None

    def get_start_date_label(self):
        return self.start_date.isoformat()[:10]

    def weeks_difference(self, date1, date2):
        delta = date2 - date1
        return delta.days / 7

    def hours_difference(self, date1, date2):
        delta = date2 - date1
        return int(math.floor(delta.total_seconds() / 3600))

    def minutes_difference(self, date1, date2):
        delta = date2 - date1
        return int(math.floor(delta.total_seconds() / 60))

    def get_week_nb_from_date(self, date):
        return self.weeks_difference(self.start_date, date)

    def get_date_from_week_nb(self, week_nb):
        return self.start_date + timedelta(days=7) * week_nb

    def iter_weeks(self):
        total_weeks = self.weeks_difference(self.start_date, self.end_date)
        for week_nb in xrange(total_weeks + 1):
            yield week_nb, self.get_date_from_week_nb(week_nb)


class Action(object):

    def __init__(self, action_set, line):
        self.line = line
        self.action_set = action_set

        self.parameters = self.get_parameters()
        if self.parameters:
            self.date = datetime.strptime(line[:19], '%Y-%m-%d %H:%M:%S')
            self.role, self.player_id = self.get_role_and_id()

            if 'action' in self.parameters:
                self.name = self.parameters['action'][0]
            else:
                self.name = None

    def get_parameters(self):
        m = re.search(r'/resource\?([^ ]*)', self.line)
        if not m:
            return None

        parameters = urlparse.parse_qs(m.group(1))
        return parameters

    def get_role_and_id(self):
        role = None
        id = None

        for cur_role in ['owner', 'player']:
            if '%s_id' % cur_role in self.parameters:
                role = cur_role
                id = self.parameters['%s_id' % cur_role][0]
                break

        if id is None:
            return None, None

        id_save = id
        # Check if this is the old format of id, which used to contain the email or name
        try:
            id = int(id)
        except ValueError:
            id = self.action_set.get_player_id_from_old_id(id)

        return role, id


class ActionSet(object):

    def __init__(self, start_date):
        # Caches of emails and name resolution
        with open('raw/email2id.json') as f:
            self.email2id = json.load(f)
        with open('raw/name2id.json') as f:
            self.name2id = json.load(f)

        self.start_date = start_date
        self.end_date = None
        self.end_date = self.get_end_date()

    def get_end_date(self):
        '''Find out end of log data'''

        end_date = datetime(1900, 1, 1, 0, 0, 0)

        for action in self.iter_actions():
            if action.date > end_date:
                end_date = action.date

        return end_date

    def iter_log_files(self):
        log_dir, log_file_base = os.path.split(WS_LOG_PATH)
        log_path_list = []
        for filename in os.listdir(log_dir):
            m = re.match('%s\.(\d+)' % log_file_base, filename)
            if m:
                log_num = int(m.group(1))
                log_path_list.append([log_num, filename])

            if log_file_base == filename:
                log_path_list.append([-1, filename])

        log_path_list.sort(key=lambda x: x[0], reverse=True)

        for log_num, log_path in log_path_list:
            yield os.path.join(log_dir, log_path)

    def iter_actions(self, start_date=None, end_date=None):
        for log_path in self.iter_log_files():
            with open(log_path) as f:
                for line in f:
                    action = Action(self, line)
                    if not action.parameters:
                        continue
                    if action.date < self.start_date or \
                            (start_date and action.date < start_date):
                        continue
                    if (self.end_date and action.date > self.end_date) or \
                            (end_date and action.date >= end_date):
                        continue
                    yield action

    def get_player_id_from_old_id(self, email_or_name):
        if email_or_name in self.name2id:
            return self.name2id[email_or_name][0]
        elif email_or_name in self.email2id:
            return self.email2id[email_or_name]
        else:
            return None


class Cohort(TimeSliced):

    def __init__(self, cohort_set, start_date):
        self.cohort_set = cohort_set
        self.start_date = start_date
        self.end_date = self.cohort_set.end_date

        self.weekly_actives = {}

    def record_action(self, action):
        # Not in current cohort
        if action.date < self.start_date:
            return False

        week_nb = self.get_week_nb_from_date(action.date)

        if week_nb == 0 or self.is_player_from_cohort(action.player_id):
            self.record_weekly_active(week_nb, action.player_id)
            return True
        else:
            return False

    def is_player_from_cohort(self, player_id):
        if self.start_date not in self.weekly_actives:
            return False
        else:
            return player_id in self.weekly_actives[self.start_date]

    def record_weekly_active(self, week_nb, player_id):
        week_date = self.get_date_from_week_nb(week_nb)
        if week_date not in self.weekly_actives:
            self.weekly_actives[week_date] = [player_id]
        elif player_id not in self.weekly_actives[week_date]:
            self.weekly_actives[week_date].append(player_id)

    def get_weekly_actives(self):
        weekly_actives = []
        for week_nb, week_date in self.iter_weeks():
            if week_date in self.weekly_actives:
                nb_active_players = len(self.weekly_actives[week_date])
            else:
                nb_active_players = 0
            weekly_actives.append([week_nb, nb_active_players])

        return {'label': self.get_start_date_label(), 'data': weekly_actives}

    def get_weekly_actives_percent(self):
        weekly_actives = [y for x, y in self.get_weekly_actives()['data']]
        weekly_actives_percent = []
        i = 0
        for nb_actives in weekly_actives[1:]:
            i += 1
            percent = round(nb_actives * 100.0 / weekly_actives[0], 1)
            weekly_actives_percent.append([i, percent])

        return {'label': self.get_start_date_label(), 'data': weekly_actives_percent}


class CohortSet(TimeSliced):

    def __init__(self, action_set):
        self.action_set = action_set
        self.start_date = self.action_set.start_date
        self.end_date = self.action_set.end_date

        self.cohorts = self.get_empty_cohorts()
        self.populate_cohorts()

    def get_empty_cohorts(self):
        cohorts = []
        for week_nb, week_date in self.iter_weeks():
            cur_cohort = Cohort(self, week_date)
            cohorts.append(cur_cohort)

        return cohorts

    def populate_cohorts(self):
        for action in self.action_set.iter_actions():
            for cur_cohort in self.cohorts:
                if cur_cohort.record_action(action):
                    break

    def get_weekly_actives(self):
        weekly_actives = []
        for cur_cohort in self.cohorts:
            cur_weekly_actives = cur_cohort.get_weekly_actives()
            weekly_actives.append(cur_weekly_actives)
        return weekly_actives

    def get_weekly_actives_percent(self):
        weekly_actives_percent = []
        for cur_cohort in self.cohorts:
            cur_weekly_actives_percent = cur_cohort.get_weekly_actives_percent()
            weekly_actives_percent.append(cur_weekly_actives_percent)
        return weekly_actives_percent

    def __iter__(self):
        for cohort in self.cohorts:
            yield cohort


class WeeklyPlayerActivity(TimeSliced):

    def __init__(self, cohort_set):
        self.cohort_set = cohort_set
        self.start_date = cohort_set.start_date
        self.end_date = cohort_set.end_date

        self.weeks = self.get_empty_weeks()
        self.populate_weeks()

    def get_empty_weeks(self):
        weeks = {}
        for week_nb, week_date in self.iter_weeks():
            weeks[week_date] = {'new_players': 0, 'recurring_players':0}

        return weeks

    def populate_weeks(self):
        for week_nb, week_date in self.iter_weeks():
            for cur_cohort in self.cohort_set:
                if week_date not in cur_cohort.weekly_actives:
                    continue

                cur_cohort_cur_week_actives = len(cur_cohort.weekly_actives[week_date])
                if cur_cohort.start_date == week_date:
                    self.weeks[week_date]['new_players'] = cur_cohort_cur_week_actives
                else:
                    self.weeks[week_date]['recurring_players'] += cur_cohort_cur_week_actives

    def get_active_players_per_week(self):
        new_players = []
        recurring_players = []
        total_players = []

        for week_date, counters in self.weeks.iteritems():
            week_timestamp = int(mktime(week_date.timetuple()) * 1000)
            new_players.append([week_timestamp, counters['new_players']])
            recurring_players.append([week_timestamp, counters['recurring_players']])
            total_players.append([week_timestamp, counters['new_players'] + counters['recurring_players']])

        # Chronological order is expected
        date_key = lambda x: x[0]
        for cur_array in [new_players, recurring_players, total_players]:
            cur_array.sort(key=date_key)

        return [{'label': 'New players', 'data': new_players},
                {'label': 'Recurring players', 'data': recurring_players},
                {'label': 'Total players', 'data': total_players}]


class ConcurrentPlayers(TimeSliced):

    def __init__(self, action_set):
        self.action_set = action_set
        self.start_date = self.action_set.end_date - timedelta(days=30)
        self.end_date = self.action_set.end_date

        self.minutes = self.get_empty_minutes()
        self.populate_minutes()

    def get_empty_minutes(self):
        minutes = {}
        minute_nb = 0
        while minute_nb < self.minutes_difference(self.start_date, self.end_date) + 1:
            minutes[minute_nb] = []
            minute_nb += 1
        return minutes

    def populate_minutes(self):
        for action in self.action_set.iter_actions(start_date=self.start_date):
            minute_nb = self.minutes_difference(self.start_date, action.date)
            if action.player_id not in self.minutes[minute_nb]:
                self.minutes[minute_nb].append(action.player_id)

    def get_concurrent_players(self):
        concurrent_players = []

        for minute_nb, player_ids in self.minutes.iteritems():
            cur_date = self.start_date + timedelta(minutes=minute_nb)
            minute_timestamp = int(mktime(cur_date.timetuple()) * 1000)
            concurrent_players.append([minute_timestamp, len(player_ids)])

        # Chronological order is expected
        date_key = lambda x: x[0]
        concurrent_players.sort(key=date_key)

        return concurrent_players

    def get_concurrent_players_trimmed(self):
        concurrent_players = self.get_concurrent_players()

        # Remove duplicate values to make the array lighter
        trimmed_concurrent_players = []
        for i in xrange(len(concurrent_players)):
            if i == 0 or i + 1 >= len(concurrent_players):
                continue
            if concurrent_players[i - 1][1] != concurrent_players[i][1] or \
               concurrent_players[i][1] != concurrent_players[i + 1][1]:
                trimmed_concurrent_players.append(concurrent_players[i])

        return [{'label': 'Concurrent players', 'data': trimmed_concurrent_players}]

    def get_time_percent_with_enough_players(self):
        time_percent_enough = []
        time_percent_not_enough = []
        time_percent_empty = []
        concurrent_players = self.get_concurrent_players()
        minute_nb = 0

        for i in xrange(self.hours_difference(self.start_date, self.end_date)):
            nb_times_enough = 0
            nb_times_nobody = 0
            for j in xrange(60):
                if concurrent_players[minute_nb][1] >= 3:
                    nb_times_enough += 1
                elif concurrent_players[minute_nb][1] == 0:
                    nb_times_nobody += 1
                minute_nb += 1

            percent_enough = round(nb_times_enough * 100 / 60, 1)
            percent_not_enough = round((60.0 - nb_times_enough) * 100 / 60, 1)
            percent_empty = round((60.0 - nb_times_nobody) * 100 / 60, 1)

            cur_date = self.start_date + timedelta(hours=1) * i
            cur_timestamp = int(mktime(cur_date.timetuple()) * 1000)
            time_percent_enough.append([cur_timestamp, percent_enough])
            time_percent_not_enough.append([cur_timestamp, percent_not_enough])
            time_percent_empty.append([cur_timestamp, percent_empty])

        return [{'label': 'Percentage of time with enough players', 'data': time_percent_enough},
                {'label': 'Percentage of time with NOT enough players', 'data': time_percent_not_enough}]


class Funnel(TimeSliced):

    def __init__(self, action_set):
        self.action_set = action_set

        self.start_date = self.action_set.start_date
        self.end_date = self.action_set.end_date

        self.steps_names = ['first_visit',
                            'registration',
                            'game_loaded',
                            'first_game_created',
                            'game_voting',
                            'game_complete',
                            'second_game',
                            'second_day']
        self.steps = self.get_empty_steps()

        self.owa_data = self.get_owa_data()
        self.process_owa_data()

        self.process_actions()

    def get_empty_steps(self):
        steps = {}
        for step_name in self.steps_names:
            for week_nb, week_date in self.iter_weeks():
                if week_nb in steps:
                    steps[week_nb][step_name] = 0
                else:
                    steps[week_nb] = {step_name: 0}

        return steps

    def get_owa_data(self):
        start_date_str = self.start_date.strftime('%Y%m%d')
        end_date_str = self.end_date.strftime('%Y%m%d')
        owa_url = '%s/api.php?owa_apiKey=%s&owa_do=getResultSet&owa_metrics=bounces,repeatVisitors,newVisitors,visits&owa_dimensions=date&owa_startDate=%s&owa_endDate=%s&owa_siteId=%s&owa_format=json' % \
                            (OWA_URL, OWA_API_KEY, start_date_str, end_date_str, OWA_SITE_ID)

        r = requests.get(owa_url)
        return json.loads(r.content)

    def process_owa_data(self):
        for row in self.owa_data['rows']:
            cur_date = datetime.strptime(row['date'], '%Y%m%d')
            week_nb = self.get_week_nb_from_date(cur_date)
            self.steps[week_nb]['first_visit'] += int(row['newVisitors'])
            self.steps[week_nb]['registration'] += int(row['newVisitors']) - int(row['bounces'])

    def process_actions(self):
        player_status = {}
        for action in self.action_set.iter_actions():
            player_id = action.player_id
            action_week_nb = self.get_week_nb_from_date(action.date)

            if player_id not in player_status:
                player_status[player_id] = {'week_nb': action_week_nb,
                                            'first_action_date': action.date,
                                            'step': 'game_loaded'}
                self.steps[action_week_nb]['game_loaded'] += 1

            player_week_nb = player_status[player_id]['week_nb']

            if action.name == 'create' and player_status[player_id]['step'] == "game_loaded":
                player_status[player_id]['step'] = 'first_game_created'
                self.steps[player_week_nb]['first_game_created'] += 1

            elif action.name == 'voting' and player_status[player_id]['step'] == "first_game_created":
                player_status[player_id]['step'] = 'game_voting'
                self.steps[player_week_nb]['game_voting'] += 1

            elif action.name == 'complete' and player_status[player_id]['step'] == "game_voting":
                player_status[player_id]['step'] = 'game_complete'
                self.steps[player_week_nb]['game_complete'] += 1

            elif (action.name == 'create' or action.name == 'join') and \
                        player_status[player_id]['step'] == "game_complete":
                player_status[player_id]['step'] = 'second_game'
                self.steps[player_week_nb]['second_game'] += 1

            elif self.hours_difference(player_status[player_id]['first_action_date'], action.date) > 15 and \
                        player_status[player_id]['step'] == "second_game":
                player_status[player_id]['step'] = 'second_day'
                self.steps[player_week_nb]['second_day'] += 1

    def get_weekly_steps_percent(self):
        weekly_step_list = []
        for week_nb, week_date in self.iter_weeks():
            week_step = {'label': week_date.isoformat()[:10], 'data': []}
            for step_nb in xrange(1, len(self.steps_names)):
                cur_step_nb = self.steps[week_nb][self.steps_names[step_nb]]
                prev_step_nb = self.steps[week_nb][self.steps_names[step_nb - 1]]

                if prev_step_nb == 0:
                    step_percent = 0
                else:
                    step_percent = cur_step_nb * 100 / prev_step_nb
                    if step_percent > 100: # Sometimes OWA drops some calls :/
                        step_percent = 50

                week_step['data'].append([step_nb, step_percent])

            # Total - ie proportion of new visitors who go through all the steps
            total_percent = self.steps[week_nb][self.steps_names[step_nb]] * 100.0 / \
                            self.steps[week_nb][self.steps_names[0]]
            week_step['data'].append([step_nb + 1, round(total_percent, 2)])

            weekly_step_list.append(week_step)

        return weekly_step_list

# Main ###################################################################

#cat $(for i in $(seq 594 -1 1) ; do echo cardstories.org_twisted.log.$i ; done) |

start_date = datetime(2011, 10, 10, 0, 0, 0)
action_set = ActionSet(start_date)
concurrent_players = ConcurrentPlayers(action_set)
cohort_set = CohortSet(action_set)
week_set = WeeklyPlayerActivity(cohort_set)
funnel = Funnel(action_set)

# Results #

data = {}

weekly_actives = cohort_set.get_weekly_actives()
data['weekly_actives'] = add_average_to_weekly_set(weekly_actives)

weekly_actives_percent = cohort_set.get_weekly_actives_percent()
data['weekly_actives_percent'] = add_average_to_weekly_set(weekly_actives_percent)

data['active_players_per_week'] = week_set.get_active_players_per_week()
data['concurrent_players'] = concurrent_players.get_concurrent_players_trimmed()
data['enough_players_percent'] = concurrent_players.get_time_percent_with_enough_players()

weekly_steps_percent = funnel.get_weekly_steps_percent()
data['funnel'] = add_average_to_weekly_set(weekly_steps_percent)

with open(JSON_OUTPUT_PATH, 'w+') as f:
    json.dump(data, f)


