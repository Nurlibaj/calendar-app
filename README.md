# Calendar App

This simple calendar app reads a public Outlook calendar in ICS format and exposes it through a Flask API. The server's local time zone can be configured through the `TIMEZONE` environment variable.

## Time zone configuration

The application calculates current time using the zone info from `TIMEZONE`. If the variable is unset, UTC is used. This zone is applied when parsing calendar events and when displaying chat message timestamps, ensuring consistent times across the app.

To run the app using the local time in the United Kingdom, set the variable to `Europe/London`:

```bash
export TIMEZONE=Europe/London
```

Make sure to set this variable in your hosting environment (for example, in Heroku configuration) so that event times and status checks reflect your local time.
