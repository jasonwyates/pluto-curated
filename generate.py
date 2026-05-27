#!/usr/bin/env python3
"""
Generate a curated Pluto TV M3U playlist + XMLTV EPG.

Pulls the live lineup/guide from Pluto's public API, keeps only the curated
channels (in order), writes:
  - playlist.m3u   (stream URLs via jmp2.uk/plu-<id>, which mints a valid
                    Pluto session token — the direct stitcher URLs only play a
                    "takedown slate" bumper)
  - epg.xml        (XMLTV guide built from each channel's `timelines`)

Standard library only. Run on a schedule (e.g. a GitHub Action) so the EPG
stays fresh — Pluto only publishes ~a day or two ahead.
"""

import datetime
import html
import json
import urllib.parse
import urllib.request

# ---- Curated channels: Pluto `_id`, in display order ------------------------
CURATED = [
    # Pinned at top
    ("649ddbfb6f29ec000874ca9e", "Supermarket Sweep"),
    # Music
    ("5f32f26bcd8aea00071240e5", "Vevo '70s"),
    ("5fd7b8bf927e090007685853", "Vevo '80s"),
    ("5fd7bb1f86d94a000796e2c2", "Vevo '90s"),
    ("5fd7bca3e0a4ee0007a38e8c", "Vevo 2K"),
    ("61d4b38226b8a50007fe03a6", "Vevo Rock"),
    ("623a1b5188ecdc0007c9ef5a", "XITE Rock x Metal"),
    ("696998915a0ae9e1b563f0c6", "Qello Concerts"),
    ("696689d13b9ce349c9be3a18", "Stingray DJAZZ"),
    ("5873fc21cad696fb37aa9054", "Live Music"),
    # Right after music videos
    ("5f36d726234ce10007784f2a", "The Bob Ross Channel"),
    ("5e84f54a82f05300080e6746", "America's Test Kitchen"),
    # Home + Food
    ("64dab9df3d48f40008868091", "The Jamie Oliver Channel"),
    ("66ff0cf663292d0008320cf8", "No Reservations"),
    # Game shows
    ("5812bfbe4ced4f7b601b12e6", "BUZZR"),
    ("5e54187aae660e00093561d6", "Game Show Central"),
    ("6036e7c385749f00075dbd3b", "Pluto TV Game Shows"),
    ("643f03b9d8436e0008edf021", "Family Feud Classic"),
    ("5f7791b8372da90007fd45e6", "The Price Is Right: The Barker Era"),
    # Comedy / classic TV
    ("5ca671f215a62078d2ec0abf", "Comedy Central Pluto TV"),
    ("545943f1c9f133a519bbac92", "MST3K"),
    ("5f15e3cccf49290007053c67", "Classic TV Drama"),
    # Movies — decades then genres
    ("5f4d878d3d19b30007d2e782", "70s Cinema"),
    ("5ca525b650be2571e3943c63", "80s Rewind"),
    ("5f4d86f519358a00072b978e", "90s Throwback"),
    ("62ba60f059624e000781c436", "00s Replay"),
    ("561c5b0dada51f8004c4d855", "Classic Movies Channel"),
    ("5cb0cae7a461406ffe3f5213", "Paramount Movie Channel"),
    ("645e7828e1979c00087b75b4", "MovieSphere by Lionsgate"),
    ("5f4d863b98b41000076cd061", "Pluto TV Staff Picks"),
    ("64b585f84ea480000838e446", "Pluto TV Icons"),
    ("5c665db3e6c01b72c4977bc2", "Pluto TV Cult Films"),
    ("5a4d3a00ad95e4718ae8d8db", "Pluto TV Comedy"),
    ("5b4e92e4694c027be6ecece1", "Pluto TV Drama"),
    ("5f4d8594eb979c0007706de7", "Pluto TV Crime Movies"),
    ("5b4e69e08291147bd04a9fd7", "Pluto TV Thrillers"),
    ("569546031a619b8f07ce6e25", "Pluto TV Horror"),
    ("5b64a245a202b3337f09e51d", "Pluto TV Fantastic"),
    ("5b4e94282d4ec87bdcbb87cd", "Pluto TV Westerns"),
    # Sci-Fi
    ("5efbd39f8c4ce900075d7698", "Star Trek"),
    ("695c32e61ca20bb8ca802eb9", "Star Trek: The Next Generation"),
    ("65c69bbfd77d450008c7ffee", "Star Trek: Deep Space Nine"),
    ("634dacf51d90320007fcd5fa", "Star Trek: Voyager"),
    # History + Science
    ("5f21ea08007a49000762d349", "Smithsonian Channel Selects"),
    ("65775d29dfed030008cb3db2", "Modern Marvels by HISTORY"),
    ("5a4d35dfa5c02e717a234f86", "Pluto TV History"),
    ("563a970aa1a1f7fe7c9daad7", "Pluto TV Science"),
    ("5bb3fea0f711fd76340eebff", "Pluto TV Military"),
    # Antiques + Nature
    ("5ce44810b421747ae467b7cd", "Antiques Roadshow UK"),
    ("636c2b3c55d2e700074105c4", "PBS Antiques Roadshow"),
    ("640a64bd73e013000893d4e0", "PBS Nature"),
    # Reality
    ("636adc255bcf470007d6e0e2", "Top Gear"),
    ("6565413e4261ca0008215320", "Pickers & Pawn"),
    ("6549322e53fc97000838febc", "Million Dollar Listing Vault"),
    ("64e561a4354251000823a0e0", "Ghost Hunters"),
    ("5e1f7e089f23700009d66303", "COPS"),
    ("627d355aa95efd00077afcc7", "Cheaters"),
    # Sports
    ("5ced7d5df64be98e07ed47b6", "NFL Channel"),
]

START_NUMBER = 1            # tvg-chno for the first curated channel
EPG_HOURS = 48              # how far ahead to request the guide


def fetch_channels():
    now = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    stop = now + datetime.timedelta(hours=EPG_HOURS)

    def enc(d):
        return urllib.parse.quote(d.strftime("%Y-%m-%d %H:%M:%S.000+0000"))

    url = f"http://api.pluto.tv/v2/channels?start={enc(now)}&stop={enc(stop)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def to_xmltv_time(iso):
    # "2026-05-27T01:40:22.000Z" -> "20260527014022 +0000"
    d = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return d.strftime("%Y%m%d%H%M%S %z")


def main():
    data = fetch_channels()
    by_id = {c.get("_id"): c for c in data}

    m3u = ["#EXTM3U"]
    chan_xml = []
    prog_xml = []

    num = START_NUMBER
    for cid, fallback_name in CURATED:
        ch = by_id.get(cid)
        if not ch or not ch.get("isStitched"):
            print(f"[WARN] missing/!stitched: {fallback_name} ({cid})")
            continue

        name = ch.get("name") or fallback_name
        logo = (ch.get("colorLogoPNG") or {}).get("path", "")
        group = ch.get("category", "")
        stream = f"https://jmp2.uk/plu-{cid}.m3u8"

        m3u.append(
            f'#EXTINF:-1 tvg-id="{cid}" tvg-chno="{num}" '
            f'tvg-logo="{logo}" group-title="{html.escape(group)}",{name}'
        )
        m3u.append(stream)

        chan_xml.append(f'  <channel id="{cid}">')
        chan_xml.append(f'    <display-name>{html.escape(name)}</display-name>')
        chan_xml.append(f'    <display-name>{num}</display-name>')
        if logo:
            chan_xml.append(f'    <icon src="{html.escape(logo)}" />')
        chan_xml.append('  </channel>')

        for t in ch.get("timelines") or []:
            try:
                start = to_xmltv_time(t["start"])
                stop = to_xmltv_time(t["stop"])
            except Exception:
                continue
            title = html.escape(t.get("title") or "Program")
            ep = t.get("episode") or {}
            desc = html.escape(ep.get("description") or "")
            prog_xml.append(f'  <programme start="{start}" stop="{stop}" channel="{cid}">')
            prog_xml.append(f'    <title lang="en">{title}</title>')
            if desc:
                prog_xml.append(f'    <desc lang="en">{desc}</desc>')
            prog_xml.append('  </programme>')

        num += 1

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u) + "\n")

    epg = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tv generator-info-name="pluto-curated">']
    epg += chan_xml + prog_xml
    epg.append('</tv>')
    with open("epg.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(epg) + "\n")

    print(f"[OK] wrote playlist.m3u ({num - START_NUMBER} channels) and epg.xml "
          f"({len(prog_xml) // 4} programmes)")


if __name__ == "__main__":
    main()
