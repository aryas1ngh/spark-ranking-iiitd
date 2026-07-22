# SPARK — Faculty PIDs needing review

Generated: 2026-07-21T20:47:35Z  |  Source: CSRankings CSV

**53** untriaged of **53** flagged, across 25 institutions.

## How to resolve

Edit `data/pid_overrides.csv` (one row per person) — the resolver reads it first and it survives every re-run:

- `set` — you found the right DBLP PID → person enters the roster as MANUAL.
- `drop` — duplicate name variant or not really CS faculty → excluded.
- `ack` — can't resolve yet, but stop alerting on it (stays listed below).

```csv
institution,csrankings_name,dblp_pid,action,note
IITM,Kamakoti Veezhinathan,80/1234,set,verified by hand
IISC,Chiru Bhattacharyya,,drop,alias of Chiranjib Bhattacharyya
IITB,Bernard Menezes,,ack,retired; no clean DBLP profile
```

| Institution | Confidence | Name | DBLP PID | Reason | Ack |
|---|---|---|---|---|---|
| IIITD | REVIEW | Pankaj Jalote | [j/PankajJalote](https://dblp.org/pid/j/PankajJalote) | DBLP affiliation does not mention this institution |  |
| IIITH | REVIEW | Deepak Gangadharan | [98/7452](https://dblp.org/pid/98/7452) | DBLP affiliation does not mention this institution |  |
| IIITH | REVIEW | Govindarajulu Regeti | [27/8325](https://dblp.org/pid/27/8325) | no publications since 2015 |  |
| IIITH | REVIEW | Kalluri R. Sarma | [02/6803](https://dblp.org/pid/02/6803) | no publications since 2015 |  |
| IIITH | REVIEW | Kannan Srinathan | — | no exact DBLP author-name match |  |
| IIITH | REVIEW | R. K. Bagga | [57/5018](https://dblp.org/pid/57/5018) | no publications since 2015 |  |
| IIITH | REVIEW | Raghu Reddy | — | no exact DBLP author-name match |  |
| IIITH | REVIEW | Rambabu Kalla | [164/3332](https://dblp.org/pid/164/3332) | no publications since 2015 |  |
| IISC | REVIEW | Chiru Bhattacharyya | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Deepak D'Souza | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Dilip P. Patil | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Filbert Minj | [45/1508](https://dblp.org/pid/45/1508) | no publications since 2015 |  |
| IISC | REVIEW | Matthew Jacob Thazhuthaveetil | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Matthew Thazhuthaveetil | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Narayanas Balakrishnan | — | no exact DBLP author-name match |  |
| IISC | REVIEW | R.C. Hansdah | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Y. Narahari | — | no exact DBLP author-name match |  |
| IISC | REVIEW | Yadati Narahari | — | no exact DBLP author-name match |  |
| IITB | REVIEW | Akash Kumar | [140/9567-3](https://dblp.org/pid/140/9567-3) | DBLP affiliation does not mention this institution |  |
| IITB | REVIEW | Arjun Nitin Bhagoji | [199/2164](https://dblp.org/pid/199/2164) | aliases resolved to multiple PIDs: ['160/8607', '199/2164'] |  |
| IITB | REVIEW | Ashutosh Kumar Gupta | — | no exact DBLP author-name match |  |
| IITB | REVIEW | Bernard Menezes | — | no exact DBLP author-name match |  |
| IITB | REVIEW | Dhananjay M. Dhamdhere | [d/DMDhamdhere](https://dblp.org/pid/d/DMDhamdhere) | no publications since 2015 |  |
| IITBHU | REVIEW | Tanima Dutta | [124/3022](https://dblp.org/pid/124/3022) | DBLP affiliation does not mention this institution |  |
| IITD | REVIEW | Rajendra Kumar | [42/7523-2](https://dblp.org/pid/42/7523-2) | DBLP affiliation does not mention this institution |  |
| IITDH | REVIEW | Vijeth J. Kotagi | [172/4519](https://dblp.org/pid/172/4519) | DBLP affiliation does not mention this institution |  |
| IITG | REVIEW | Jain Arijit Sur | — | no exact DBLP author-name match |  |
| IITG | REVIEW | Rajasekhar Inkulu | — | no exact DBLP author-name match |  |
| IITG | REVIEW | S. V. Rao | — | no exact DBLP author-name match |  |
| IITG | REVIEW | Sushanta Karmakar | [26/3091](https://dblp.org/pid/26/3091) | no publications since 2015 |  |
| IITGN | REVIEW | Yogesh Kumar Meena | [66/10604](https://dblp.org/pid/66/10604) | no publications since 2015 |  |
| IITH | REVIEW | Ch. Sobhan Babu | — | no exact DBLP author-name match |  |
| IITH | REVIEW | U. Ramakrishna | [91/10859](https://dblp.org/pid/91/10859) | aliases resolved to multiple PIDs: ['256/5234', '91/10859'] |  |
| IITJ | REVIEW | Deepak Mishra | [65/6758-1](https://dblp.org/pid/65/6758-1) | DBLP affiliation does not mention this institution |  |
| IITJMU | REVIEW | Samaresh Bera | [71/8917](https://dblp.org/pid/71/8917) | DBLP affiliation does not mention this institution |  |
| IITK | REVIEW | Sunil Easaw Simon | — | no exact DBLP author-name match |  |
| IITK | REVIEW | Sunil Simon | [15/4902](https://dblp.org/pid/15/4902) | DBLP affiliation does not mention this institution |  |
| IITKGP | REVIEW | Chittaranjan Mandal | [175/5896](https://dblp.org/pid/175/5896) | DBLP affiliation does not mention this institution |  |
| IITKGP | REVIEW | Jayanta Mukherjee | — | no exact DBLP author-name match |  |
| IITKGP | REVIEW | Pabitra Mitra | [m/PabitraMitra](https://dblp.org/pid/m/PabitraMitra) | DBLP affiliation does not mention this institution |  |
| IITM | REVIEW | Harish Guruprasad Ramaswamy | — | no exact DBLP author-name match |  |
| IITM | REVIEW | John Augustine | — | no exact DBLP author-name match |  |
| IITM | REVIEW | Kamakoti Veezhinathan | — | no exact DBLP author-name match |  |
| IITM | REVIEW | Prashanth Lakshmanrao Ananthapadmanabharao | [90/3161](https://dblp.org/pid/90/3161) | DBLP affiliation does not mention this institution |  |
| IITM | REVIEW | Yadu Vasudev | [23/10305](https://dblp.org/pid/23/10305) | no publications since 2015 |  |
| IITMANDI | REVIEW | Dileep Aroor Dinesh | — | no exact DBLP author-name match |  |
| IITMANDI | REVIEW | Renu Rameshan | — | no exact DBLP author-name match |  |
| IITR | REVIEW | P. Sateesh Kumar | [14/7491](https://dblp.org/pid/14/7491) | no publications since 2015 |  |
| IITR | REVIEW | Partha Pratim Roy | — | no exact DBLP author-name match |  |
| IITRPR | REVIEW | Jung Hyun Jun | — | no exact DBLP author-name match |  |
| IITRPR | REVIEW | S. R. S. Iyengar | — | no exact DBLP author-name match |  |
| IITTP | REVIEW | Ajin George Joseph | — | no exact DBLP author-name match |  |
| IITTP | REVIEW | Ajin Joseph | [171/3116](https://dblp.org/pid/171/3116) | DBLP affiliation does not mention this institution |  |
