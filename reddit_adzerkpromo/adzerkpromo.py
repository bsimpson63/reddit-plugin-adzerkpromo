from collections import namedtuple
from decimal import Decimal, ROUND_DOWN
import json

import adzerk
from pylons import g
import requests

from r2.lib import (
    authorize,
    organic,
    promote,
)
from r2.lib.pages.things import default_thing_wrapper
from r2.lib.pages.trafficpages import get_billable_traffic
from r2.lib.template_helpers import replace_render
from r2.lib.hooks import HookRegistrar
from r2.models import (
    Account,
    CampaignBuilder,
    Frontpage,
    Link,
    PromotionLog,
    Subreddit,
)
from r2.models.traffic import get_traffic_last_modified


adzerk.set_key(g.adzerk_key)
hooks = HookRegistrar()

ADZERK_IMPRESSION_BUMP = 500    # add extra impressions to the number we
                                # request from adzerk in case their count
                                # is lower than our internal traffic tracking


def date_to_adzerk(d):
    return d.strftime('%m/%d/%Y')


def srname_to_keyword(srname):
    return srname or 'reddit.com'


def render_link(link, campaign):
    author = Account._byID(link.author_id, data=True)
    return json.dumps({
        'link': link._fullname,
        'campaign': campaign._fullname,
        'title': link.title,
        'author': author.name,
        'target': campaign.sr_name,
    })


def update_campaign(link):
    """Add/update a reddit link as an Adzerk Campaign"""
    if hasattr(link, 'adzerk_campaign_id'):
        az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)
    else:
        az_campaign = None

    d = {
        'AdvertiserId': g.adzerk_advertiser_id,
        'IsDeleted': False,
        'IsActive': True,
        'Price': 0,
    }

    if az_campaign:
        print 'updating adzerk campaign for %s' % link._fullname
        for key, val in d.iteritems():
            setattr(az_campaign, key, val)
        az_campaign._send()
    else:
        print 'creating adzerk campaign for %s' % link._fullname
        d.update({
            'Name': link._fullname,
            'Flights': [],
            'StartDate': date_to_adzerk(datetime.datetime.now(g.tz)),
        })
        az_campaign = adzerk.Campaign.create(**d)
        link.adzerk_campaign_id = az_campaign.Id
        link._commit()
    return az_campaign


def update_creative(link, campaign):
    """Add/update a reddit link/campaign as an Adzerk Creative"""
    if hasattr(campaign, 'adzerk_creative_id'):
        az_creative = adzerk.Creative.get(campaign.adzerk_creative_id)
    else:
        az_creative = None

    title = '-'.join((link._fullname, campaign._fullname))
    d = {
        'Body': title,
        'ScriptBody': render_link(link, campaign),
        'AdvertiserId': g.adzerk_advertiser_id,
        'AdTypeId': g.adzerk_ad_type,
        'Alt': link.title,
        'Url': link.url,
        'IsHTMLJS': True,
        'IsSync': False,
        'IsDeleted': False,
        'IsActive': True,
    }

    if az_creative:
        print 'updating adzerk creative for %s %s' % (link._fullname,
                                                      campaign._fullname)
        for key, val in d.iteritems():
            setattr(az_creative, key, val)
        az_creative._send()
    else:
        print 'creating adzerk creative for %s %s' % (link._fullname,
                                                      campaign._fullname)
        d.update({'Title': title})
        az_creative = adzerk.Creative.create(**d)
        campaign.adzerk_creative_id = az_creative.Id
        campaign._commit()
    return az_creative


def update_flight(link, campaign):
    """Add/update a reddit campaign as an Adzerk Flight"""
    if hasattr(campaign, 'adzerk_flight_id'):
        az_flight = adzerk.Flight.get(campaign.adzerk_flight_id)
    else:
        az_flight = None

    az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)

    d = {
        'StartDate': date_to_adzerk(campaign.start_date),
        'EndDate': date_to_adzerk(campaign.end_date),
        'Price': campaign.cpm,
        'OptionType': 1, # 1: CPM, 2: Remainder
        'Impressions': campaign.daily_bid,  # Impressions field is the Goal
        'IsUnlimited': False,
        'IsFullSpeed': not campaign.serve_even,
        'Keywords': srname_to_keyword(campaign.sr_name),
        'CampaignId': az_campaign.Id,
        'PriorityId': g.adzerk_priority_id, # TODO: property of PromoCampaign
        'IsDeleted': False,
        'IsActive': True,
        'GoalType': 2, # 1: Impressions, 2: Percentage
        'RateType': 2, # 2: CPM
        'IsFreqCap': False,
    }

    if az_flight:
        print 'updating adzerk flight for %s' % campaign._fullname
        for key, val in d.iteritems():
            setattr(az_flight, key, val)
        az_flight._send()
    else:
        print 'creating adzerk flight for %s' % campaign._fullname
        d.update({'Name': campaign._fullname})
        az_flight = adzerk.Flight.create(**d)
        campaign.adzerk_flight_id = az_flight.Id
        campaign._commit()
    return az_flight


def update_cfmap(link, campaign):
    """Add/update a CreativeFlightMap.
    
    Map the the reddit link (adzerk Creative) and reddit campaign (adzerk
    Flight).

    """

    az_campaign = adzerk.Campaign.get(link.adzerk_campaign_id)
    az_creative = adzerk.Creative.get(campaign.adzerk_creative_id)
    az_flight = adzerk.Flight.get(campaign.adzerk_flight_id)

    if hasattr(campaign, 'adzerk_cfmap_id'):
        az_cfmap = adzerk.CreativeFlightMap.get(az_flight.Id,
                                                campaign.adzerk_cfmap_id)
    else:
        az_cfmap = None

    d = {
        'SizeOverride': False,
        'CampaignId': az_campaign.Id,
        'PublisherAccountId': g.adzerk_advertiser_id,
        'Percentage': 100,  # Each flight only has one creative (what about autobalanced)
        'DistributionType': 2, # 2: Percentage, 1: Auto-Balanced, 0: ???
        'Iframe': False,
        'Creative': {'Id': az_creative.Id},
        'FlightId': az_flight.Id,
        'Impressions': campaign.impressions + ADZERK_IMPRESSION_BUMP,
        'IsDeleted': False,
        'IsActive': True,
    }

    if az_cfmap:
        print 'updating adzerk cfmap for %s %s' % (link._fullname,
                                                   campaign._fullname)
        for key, val in d.iteritems():
            setattr(az_cfmap, key, val)
        az_cfmap._send()
    else:
        print 'creating adzerk cfmap for %s %s' % (link._fullname,
                                                   campaign._fullname)
        az_cfmap = adzerk.CreativeFlightMap.create(az_flight.Id, **d)
        campaign.adzerk_cfmap_id = az_cfmap.Id
        campaign._commit()
    return az_cfmap


def update_adzerk(link, campaign):
    az_campaign = update_campaign(link)
    az_creative = update_creative(link, campaign)
    az_flight = update_flight(link, campaign)
    az_cfmap = update_cfmap(link, campaign)
    text = ('%s/%s updated to %s, %s, %s, %s' % (az_campaign, az_creative,
                                                 az_flight, az_cfmap))
    PromotionLog.add(link, text)


@hooks.on('promote.make_daily_promotions')
def make_adzerk_promotions(offset=0):
    # make sure is_charged_transaction and is_accepted are the only criteria
    # for a campaign going live!

    for link, campaign, weight in promote.accepted_campaigns(offset=offset):
        if (authorize.is_charged_transaction(campaign.trans_id, campaign._id)
            and promote.is_accepted(link)):
            update_adzerk(link, campaign)


@hooks.on('promotion.void')
def deactivate_link(link):
    # Can't deactivate creative without the campaign, should be ok
    az_campaign = update_campaign(link)
    az_campaign.IsActive = False
    az_campaign._send()


@hooks.on('campaign.void')
def deactivate_campaign(campaign):
    # Do we need to deactivate the link objects and map?
    az_flight = update_flight(campaign)
    az_flight.IsActive = False
    az_flight._send()


@hooks.on('js_config')
def adzerkpromo_js_config(config):
    config['adzerkpromo'] = {
        'site_id': g.adzerk_site_id,
        'advertiser_id': g.adzerk_advertiser_id,
        'priority_id': g.adzerk_priority_id,
        'channel_id': g.adzerk_channel_id,
        'publisher_id': g.adzerk_publisher_id,
        'network_id': g.adzerk_network_id,
        'ad_type': g.adzerk_ad_type,
    }


def get_billable_impressions(campaign):
    billable_traffic = get_billable_traffic(campaign)
    billable_impressions = sum(imp for date, (imp, click) in billable_traffic)
    return billable_impressions


def get_billable_amount(budget, impressions, cpm):
    value_delivered = impressions / 1000 * cpm
    billable_amount = min(budget, value_delivered)
    return Decimal(billable_amount).quantize(Decimal('.01'),
                                             rounding=ROUND_DOWN)


# TODO: Do we want to send an email whenever any campaign ends, not just when
# the whole link is deactivated?
# Make expired_campaigns in make_daily_promotions
def finalize_completed_campaigns(daysago=1):
    # PromoCampaign.end_date is utc datetime with year, month, day only
    now = datetime.datetime.now(g.tz)
    date = now - datetime.timedelta(days=daysago)
    date = date.replace(hour=0, minute=0, second=0, microsecond=0)

    # check that traffic is up to date
    last_modified = get_traffic_last_modified().replace(tzinfo=g.tz)
    if last_modified < date:
        raise ValueError("Can't finalize campaigns finished on %s. Most recent"
                         " traffic data is from %s." % (date, last_modified))

    q = PromoCampaign._query(PromoCampaign.c.end_date == date,
                             # exclude no transaction and freebies
                             PromoCampaign.c.trans_id > 0,
                             data=True)
    campaigns = list(q)
    links = Link._byID([camp.link_id for link in links], data=True)

    for camp in campaigns:
        if hasattr(camp, 'refund_amount'):
            continue

        link = links[camp.link_id]
        billable_impressions = get_billable_impressions(camp)
        billable_amount = get_billable_amount(camp.bid, billable_impressions,
                                              camp.cpm)

        if billable_amount >= camp.bid:
            text = ('%s completed with $%s billable (%s impressions @ $%s).'
                    % (camp, billable_amount, billable_impressions, camp.cpm))
            PromotionLog.add(link, text)
            refund_amount = 0.
        else:
            refund_amount = camp.bid - billable_amount
            user = Account._byID(link.author_id, data=True)
            try:
                success = authorize.refund_transaction(user, camp.trans_id,
                                                       camp._id, refund_amount)
            except authorize.AuthorizeNetException as e:
                text = ('%s $%s refund failed' % (camp, refund_amount))
                PromotionLog.add(link, text)
                g.log.debug(text + ' (response: %s)' % e)
                continue
            text = ('%s completed with $%s billable (%s impressions @ $%s).'
                    ' %s refunded.' % (camp, billable_amount,
                                       billable_impressions, camp.cpm,
                                       refund_amount))
            PromotionLog.add(link, text)

        camp.refund_amount = refund_amount
        camp._commit()


# replacements for r2.lib.promote
AdzerkResponse = namedtuple('AdzerkResponse',
                    ['link', 'campaign', 'target', 'imp_pixel', 'click_url'])

def adzerk_request(keywords, timeout=0.1):
    data = {
        "placements": [
            {
              "divName": "div1",
              "networkId": g.adzerk_network_id,
              "siteId": g.adzerk_site_id,
              "adTypes": [g.adzerk_ad_type]
            },
          ],
          'keywords': keywords,
    }

    url = 'http://engine.adzerk.net/api/v2'
    headers = {'content-type': 'application/json'}

    try:
        r = requests.post(url, data=json.dumps(data), headers=headers,
                          timeout=timeout)
    except requests.exceptions.Timeout:
        g.log.info('adzerk request timeout')
        return None

    response = json.loads(r.text)
    decision = response['decisions']['div1']

    if not decision:
        return None

    imp_pixel = decision['impressionUrl']
    click_url = decision['clickUrl']
    body = json.loads(decision['contents'][0]['body'])
    campaign = body['campaign']
    link = body['link']
    target = body['target']
    return AdzerkResponse(link, campaign, target, imp_pixel, click_url)


def get_adzerk_promo(user, site):
    srids = promote.has_live_promos(user, site)
    if not srids:
        return

    if '' in srids:
        srnames = [Frontpage.name]
        srids.remove('')
    else:
        srnames = []

    srs = Subreddit._byID(srids, data=True, return_dict=False)
    srnames.extend([sr.name for sr in srs])
    response = adzerk_request(srnames)

    if not response:
        return

    promo_tuples = [promote.PromoTuple(response.link, 1., response.campaign)]
    builder = CampaignBuilder(promo_tuples,
                              keep_fn=organic.keep_fresh_links)
    promoted_links = builder.get_items()[0]
    if promoted_links:
        w = promoted_links[0]
        w.adserver_imp_pixel = response.imp_pixel
        w.adserver_click_url = response.click_url
        return w
