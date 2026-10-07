Yes — we can adapt our existing paper system for this, and I think we have a more dependable starting point than scraping Google Scholar or relying entirely on email alerts.

We give the system a list of authors and confirm which researcher each name refers to. It then checks a scholarly publication database, OpenAlex, each day for newly listed papers. It remembers what it has already seen, checks for duplicates, and saves new papers to our paper system before sharing them in Slack.

For Slack, we have built one weekly summary, with individual paper cards in a thread. Each card includes the title, authors, publication details, a link to the paper, and feedback buttons. We can also add authors from Slack by reviewing matching author profiles, rather than editing a spreadsheet.

It runs on our existing AWS setup, so nobody needs to keep a laptop or lab computer running. Google Scholar profiles can help us identify authors, but the monitoring itself does not scrape Scholar pages. Scholar email alerts could be added later as a supplementary source if we find coverage gaps.

The 82 AC members are now on the list: 81 have matched publication profiles, and one still needs an identity check. We have saved 163 recent papers as the starting catalogue and tested real Slack messages and feedback. The pilot sends only to my private conversation with the bot; we can consider a shared channel after reviewing the results.

Publication databases can still have indexing delays or incorrect author matches. Those cases remain visible and correctable. This approach gives us a more structured and maintainable starting point than parsing alert emails, while leaving email alerts available as a backup source if needed.
