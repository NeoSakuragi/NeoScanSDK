# Brawler admin

`index.html` = https://canneji.duckdns.org/brawler-admin/ : one page with every Brawler admin tool as tabs
(Players, Live wall, Sessions, Tickets, Throws, Factory, Lab, Decisions), each tab the existing page in a frame.
Behind the Oros login + the `brawler_admin` tag (nginx `auth_request /brawler-admin-auth`, block
`# >>> brawler-admin` in sites-enabled/kanji; login page = the Factory's copy). Deploy:
`scp index.html root@195.201.91.211:/data/brawler-admin/index.html`.
