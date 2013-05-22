from r2.lib.plugin import Plugin
from r2.lib.configparse import ConfigValue
from r2.lib.js import Module

class AdzerkPromo(Plugin):
    needs_static_build = True

    config = {
        ConfigValue.int: [
            'adzerk_site_id',
            'adzerk_advertiser_id',
            'adzerk_priority_id',
            'adzerk_channel_id',
            'adzerk_publisher_id',
            'adzerk_network_id',
            'adzerk_ad_type',
        ],
    }

    js = {
        'reddit-init': Module('reddit-init.js',
            'adzerkspotlight.js',
        )
    }

    def load_controllers(self):
        import r2.lib.promote
        from reddit_adzerkpromo import adzerkpromo
        r2.lib.promote.get_single_promo = adzerkpromo.get_adzerk_promo
        adzerkpromo.hooks.register_all()
