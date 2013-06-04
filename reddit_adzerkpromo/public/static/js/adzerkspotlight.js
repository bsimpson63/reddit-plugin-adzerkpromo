r.spotlight.requestPromo = function() {
  return $.ajax({
      type: "POST",
      url: 'http://engine.adzerk.net/api/v2/',
      data: JSON.stringify({
          'placements': [
              {
                  'divName': 'div1',
                  'networkId': r.config.adzerkpromo.network_id,
                  'siteId': r.config.adzerkpromo.site_id,
                  'adTypes': [r.config.adzerkpromo.ad_type]
              }
          ],
          'keywords': reddit.post_site ? [reddit.post_site] : this.frontpage_srs
      }),
      dataType: 'json',
      contentType: 'application/json'
    }).pipe(function(data){
      var decisions = data['decisions'],
          div = decisions['div1']
      if (div) {
          var adId = div['adId'],
              creativeId = div['creativeId'],
              flightId = div['flightId'],
              campaignId = div['campaignId'],
              impressionPixel = div['impressionUrl'],
              clickUrl = div['clickUrl'],
              contents = div['contents'][0],
              adType = contents['type'],
              body = JSON.parse(contents['body']),
              link = body.link,
              campaign = body.campaign,
              promo = r.spotlight.fetchPromo(link, campaign)
          $.when(promo).done(function(promo) {
              promo.data('adserverImpPixel', impressionPixel)
              promo.data('adserverClickUrl', clickUrl)
          })
          return promo
      } else {
          return false
      }
    })
}
