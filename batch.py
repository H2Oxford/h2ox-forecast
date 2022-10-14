import os

from main import do_tigge

from datetime import datetime
from h2ox.forecast.slackbot import SlackMessenger
    
if __name__=="__main__":
    
    token=os.environ.get("SLACKBOT_TOKEN")
    target=os.environ.get("SLACKBOT_TARGET")
    
    if token is not None and target is not None:

        slackmessenger = SlackMessenger(
            token=token,
            target=target,
            name="h2ox-tigge",
        )
    else:
        slackmessenger=None
        
    do_tigge(today=datetime.now(), slackmessenger=slackmessenger)