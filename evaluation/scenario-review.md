# Scenario review checklist

Status: **accepted provisionally**; see `scenario-approval.md` for caveats

Draft SHA-256: `544ec158523cce4968d797e1b5270f877b57a09e9ac5fa871f42c77efea5449b`

Approve only after checking that the selected titles, artists, genres,
feature values, history order, and requested moods are plausible.

## Single-track histories

| Approve | Scenario | Track | Artist | Genre | Energy | Valence | Acousticness | Tempo |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| [ ] | single_happy_anchor | East Bound and Down | The Po' Ramblin' Boys;Bronwyn Keith-Hynes;Jason Carter | bluegrass | 0.704 | 0.850 | 0.537 | 124.987 |
| [ ] | single_energetic_anchor | Turn Da Beat Up! | Level | metalcore | 0.900 | 0.460 | 0.141 | 176.014 |
| [ ] | single_calm_anchor | Don't Leave Without Taking Your Silver | George Jones | honky-tonk | 0.205 | 0.309 | 0.698 | 87.049 |
| [ ] | single_sad_anchor | Conversa de Filho | Gabriela Rocha | gospel | 0.233 | 0.170 | 0.609 | 107.383 |

## Coherent history families

Each H1/H3/H5 family is nested. The table shows the full H5 order
from oldest to newest.

| Approve family | Family | Ordered H5 tracks | Artists |
| --- | --- | --- | --- |
| [ ] | coherent_pop | Kanja Poovu Kannala (From "Viruman") → abcdefu → Gulabi Aankhen → Yaanji - From "Vikram Vedha" → Mitwa | Yuvan Shankar Raja;Sid Sriram → GAYLE → Sanam → Sam C.S.;Anirudh Ravichander;Shakthisree Gopalan → Shankar-Ehsaan-Loy;Shankar Mahadevan;Caralisa Monteiro;Shafqat Amanat Ali |
| [ ] | coherent_rock | Limón y Sal → Gone, Gone, Gone → Infinity → Street Fighting Man → Don't Stop Believin' | Julieta Venegas → Phillip Phillips → Jaymes Young → Rod Stewart → Journey |
| [ ] | coherent_hip_hop | Penthouse → Hoyna Hoyna → Urvashi → Odhani (From "Made in China") → Ram Ram | Wiz Khalifa;Snoop Dogg → Anirudh Ravichander;Inno Genga → Yo Yo Honey Singh → Sachin-Jigar;Darshan Raval;Neha Kakkar → MC SQUARE |

## Transition/conflicting histories

The first three tracks are older source-mood evidence; the last two
are recent target-mood evidence.

| Approve | Scenario | Older source tracks | Recent target tracks | Requested mood |
| --- | --- | --- | --- | --- |
| [ ] | transition_calm_to_energetic | Kingdoms of Ice → Ya Se Te Fue El Tren → Старая лестница | Senta Pros Bandido → Playing In The Dark | energetic |
| [ ] | transition_energetic_to_calm | Ela Ficou Chapada → Botada Quente → Determination (Rock Lee Rap) | Intriago → The Wheels on the Bus | calm |
| [ ] | transition_sad_to_happy | Every Time It Rains → Breathe - Live → Compassion | Rhinestone Eyes → Never Forget My Love | happy |
| [ ] | transition_happy_to_sad | Aquella Solitaria Vaca Cubana → C’Mon Everybody → 旅立ち | De Volta Pro Aconchego → Proud | sad |

## Mood-only controls

| Approve | Scenario | Requested mood | Applicable algorithms |
| --- | --- | --- | --- |
| [ ] | mood_only_happy | happy | random, context_mmr |
| [ ] | mood_only_energetic | energetic | random, context_mmr |
| [ ] | mood_only_calm | calm | random, context_mmr |
| [ ] | mood_only_sad | sad | random, context_mmr |

## Approval decision

- [x] Accept all scenarios as written, provisionally.
- [ ] Request replacements listed below.

Replacement requests:

- Scenario ID:
- Track(s) to replace:
- Reason:

The accepted copy is `scenarios.json`; this draft checklist is kept for provenance.
