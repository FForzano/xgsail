# New entity-realtion (ER) diagram project
## users
id: primary key
email
password_hash
first_name
last_name
dob: day of birth (opzionale)
terms_and_conditions
is_active
is_superadmin
profile_image_id: riferimento a images
status: inactive|active|deleted
password_reset_token
created_at
updated_at
deleted_at

## auth_refresh_tokens
id
user_id
token_hash
family_id
prev_id
issued_at
expires_at
revoked_at
user_agent

## user_roles
id
user_id
role_id
scope_club_id: opzionale

## roles
id
name
description

## permissions
id
key
description

## role_permissions
id
role_id
permission_id

## boat_classes
id
name
description
logo_id: riferimento a images
created_at

## boats
id
name
boat_class_id: FK boat_classes.id, opzionale
sail_number
loa_m
cert_id: for. key for files
mbsa_id: for. key for files
notes
club_id: opzionale (indica che la barca è stazionata in un club)
created_at
updated_at

## polar_points
id
class_id      (FK boat_classes.id, nullable)
boat_id       (FK boats.id, nullable)
session_id    (FK sessions.id, nullable)
source        reference | empirical
twa_deg
tws_kts
speed_kts
vmg_kts       (nullable — soprattutto empirico)
sample_count  (nullable — solo empirico)
updated_at

vincolo: esattamente uno tra class_id, boat_id e session_id deve essere
valorizzato

nota: tre livelli di granularità nella stessa tabella — class_id+reference =
curva di classe (es. Seapilot); boat_id+empirical = aggregato storico di
tutte le sessioni della barca (sample_count cresce nel tempo); session_id+
empirical = polare specifico di una singola uscita. boat_id non è duplicato
su session_id perché risalibile via sessions.boat_id.

## boat_photos
id
boat_id
image_id

## images
id
ref: riferimento per s3/minio
status: uploaded|processed|deleted
created_at
created_by
deleted_at
deleted_by

## files
id
ref: riferimento per s3/minio
status: uploaded|processed|deleted
created_at
created_by
deleted_at
deleted_by

## user_boats
id
user_id
boat_id
role: owner|admin|visitor
default_sailing_role: skipper|crew

note: la relazione è molti a molti (un user può avere più barche e una barca può
avere più user)

## clubs
id
name
description
address_line_1      - - via + numero civico (o linea principale libera)
address_line_2       -- opzionale: interno, piano, edificio, c/o
city                 -- città/località
state_province       -- stato/provincia/regione (obbligatorio in US/CA/AU, spesso vuoto altrove)
postal_code          -- CAP/ZIP — formato libero (alfanumerico: es. UK, Canada)
country              -- meglio come codice ISO 3166-1 alpha-2 (es. "IT", "US")
invece di stringa libera
lat
lng
founded_year        -- opzionale, dato "storico" tipico di un circolo velico
website
contact_email
logo_id            -- branding nella UI, badge sulle regate --> for. key verso images
is_active           -- disattivare un club senza perdere lo storico (regate, membri, barche passate)
created_at
updated_at

## user_clubs
id
user_id
club_id
status: invited|active|deleted
created_at
deleted_at

## groups
id
name
description
profile_image_id: riferimento a images
visibility               -- public|private — public = scopribile e leggibile
                             da chiunque, private = solo membri (join solo
                             su invito in entrambi i casi)
created_by
created_at
deleted_by
deleted_at

## user_groups
id
user_id
group_id
role: owner|admin|member
created_at
deleted_at

## regattas
id
name
description
club_id
class_id            -- (opzionale) classe/flotta principale (una regatta è tipicamente mono-classe)
scoring_system       -- low_point | bonus_point | custom
start_date
end_date
status                -- scheduled|active|completed

## race_days
id
regatta_id           -- nullable: race_day "libero" non legato a una regatta
date
notes

## races
id
race_day_id
race_number           -- race 1, 2, 3 dello stesso giorno
status                -- scheduled|started|finished|abandoned
start_time

## marks
id
activity_id           -- non race_id: ogni activity (race O training) può avere le sue boe
mark_role            -- pin|rc|windward|leeward|gate_port|gate_stbd|offset|drill
lat
lng
set_at

nota: le boe sono un'istanza per-activity (posizionate via GPS ogni giorno), non
un template di percorso riutilizzabile. Agganciate ad activity_id (non a
race_id) così anche un allenamento (activities.type=training, senza regata)
può avere le sue boe — es. bastone di partenza o boa singola per esercitarsi
sulle virate. Per le boe di una race specifica: activity WHERE race_id = X →
marks WHERE activity_id = quella.

## results
id
race_id
boat_id
session_id           -- nullable: risultato inseribile anche senza traccia GPS
finish_time
elapsed_time
corrected_time        -- se si usa rating/handicap
position
score
status                -- finished|dnf|dns|dsq|ocs|ret

## activities
id
name
type              -- race | training | solo
club_id            -- nullable
race_id             -- nullable, idem
created_by
group_id
visibility          -- public|club|group|private
started_at
ended_at

nota: raggruppa N sessioni (barche) nello stesso intervallo di tempo a
prescindere dal fatto che sia una regata. Uscita in solo → activity con una
sola session; uscita di gruppo → activity con N sessions, type=training,
nessuna regata collegata; regata tracciata → type=race + race_id valorizzato.

## sessions
id
activity_id
boat_id
started_at
ended_at
status                 -- derivato/aggregato dagli status dei session_uploads collegati

nota: source_type/device_id/import_id/raw_ref NON stanno più qui — una session
può avere più device che contribuiscono dati contemporaneamente (es. l'E1 sulla
barca + uno smartwatch per ogni membro dell'equipaggio), quindi quella
relazione vive in session_uploads (una riga per ogni device/import).

## session_crew
id
session_id
user_id
sailing_role        -- skipper | crew | guest — ruolo effettivo per QUESTA uscita
created_at

nota: istanza reale di chi era a bordo per quella sessione, distinta dal
default in user_boats.default_sailing_role (che resta l'anagrafica/default).
Un utente non deve necessariamente essere già associato alla barca in
user_boats per comparire qui (es. ospite occasionale).

## session_photos
id
session_id
image_id
created_by            -- opzionale, chi ha caricato la foto (può essere un crew member)
created_at

## session_videos
id
session_id
file_id                -- FK files.id (video, non "image": riusa l'entità files
                            generica già usata per cert_id/mbsa_id in boats)
created_by
created_at

nota: relazione uno-a-molti-a-molti come boat_photos — una session può avere N
foto e N video, ognuno caricato da chi era a bordo (session_crew) o dal boat
owner. I video passano da files (non images) perché files è già l'entità
generica per blob non-immagine nello schema.

## device_types
id
name                 -- "SailFrames E1", "SailFrames B", "Apple Watch", "Garmin Instinct", "Generic GPX"
category              -- boat_tracker | wearable
default_sensors        -- opzionale, lista sensori tipici, solo informativo per
la UI
parser_key             -- identificatore dell'adapter di ingestione (es. "sailframes_e1_csv", "garmin_fit", "generic_gpx")


## devices
id
device_type_id
external_id             -- seriale hardware / UUID BLE / MAC
owner_user_id             -- nullable — dispositivo personale (es. smartwatch di un socio)
owner_boat_id               -- nullable — dispositivo installato stabilmente su una barca
owner_club_id                 -- nullable — dispositivo ad uso dell'intero club (non legato
                                  a una singola barca/utente, es. device della barca comitato)
nickname
registered_at
status                     -- unclaimed|claimed|revoked
claim_code                  -- codice pairing generato per il claim (nullable dopo claim)
claim_code_expires_at         -- finestra di validità del claim_code
claimed_at                      -- quando è avvenuto il claim (distinto da registered_at)
claimed_by                        -- user_id che ha eseguito il claim
api_key_hash                       -- hash della device_api_key emessa al claim (mai
                                       salvata in chiaro); rigenerabile via rotate-key
                                       senza rifare il claim

nota: registrazione self-service via claim token/pairing code (external_id +
codice mostrato dal device o generato in app, da inserire entro una finestra
di tempo) — niente provisioning centralizzato da admin, perché anche gli E1
possono essere autocostruiti da un socio qualunque in qualunque circolo, non
solo dalla fleet ufficiale. owner_user_id/owner_boat_id restano l'assegnazione
CORRENTE (può cambiare, es. device trasferito), mentre claim_code*/claimed_at/
claimed_by tracciano l'evento di prima associazione per audit.

vincolo: owner_user_id, owner_boat_id e owner_club_id sono mutuamente
esclusivi — al più uno dei tre valorizzato (tutti NULL = unclaimed), stesso
pattern di polar_points.

## imports
id
uploaded_by             -- user_id
original_filename
raw_ref                   -- riferimento S3 al file grezzo caricato
imported_at
status                     -- pending|processed|failed

nota: raw_ref resta qui per tracciare il file anche se il parsing fallisce
prima che una session/session_upload venga creata.

## session_uploads
id
session_id
source_type          -- device | manual_import
device_id             -- nullable, valorizzato solo se source_type=device
import_id              -- nullable, valorizzato solo se source_type=manual_import
subject_type            -- boat | crew_member — a chi si riferisce QUESTO device
subject_user_id           -- valorizzato solo se subject_type=crew_member (dovrebbe
                              essere presente in session_crew per la stessa session)
raw_ref                     -- bundle grezzo di QUESTO device/import (S3 path/prefix,
                                es. raw/E1/{date}/ oppure = imports.raw_ref se da import)
sequence_number               -- default 0 — ordine del chunk per questo device/import
                                  nella sessione (0 = unico/primo caricamento)
is_final                        -- default true — indica se questo è l'ultimo chunk
                                    che completa il contributo del device alla sessione
uploaded_at
status                        -- pending|processing|processed|failed

nota: una session può avere N session_uploads (un E1 sulla barca + uno
smartwatch per ogni membro dell'equipaggio = N righe), ognuna col proprio
raw_ref. Da ogni session_upload derivano uno o più session_streams (l'E1 ne
produce 4: gps/imu/wind/pressure; uno smartwatch tipicamente 1: heart_rate).

nota: sequence_number/is_final abilitano caricamenti intermedi (live tracking)
mantenendo semplice il caso attuale a caricamento unico (sequence_number=0,
is_final=true di default). session_streams viene generato/consolidato solo
quando arriva la riga con is_final=true per quel (session_id, device_id) — i
chunk intermedi (is_final=false) restano dati grezzi parziali, utili solo per
un'eventuale vista live, senza toccare la pipeline di processing esistente.

vincolo: chiave univoca (session_id, device_id, sequence_number) al posto di
(session_id, device_id).

## session_streams
id
session_upload_id           -- FK a session_uploads (non più device_id/import_id diretti)
sensor_type                    -- gps | imu | wind | pressure | heart_rate | other
sample_rate_hz
data_ref                         -- riferimento S3 al file processato/normalizzato,
                                     derivato dal raw_ref del suo session_upload
                                     (dati grezzi 10Hz NON in DB)
row_count

## session_stats
session_id
distance_m
avg_speed_kts
max_speed_kts
duration_s
avg_polar_pct        -- nullable — richiede dati vento (onboard o wind_observations)
max_polar_pct        -- nullable — idem
computed_at

nota generale: i dati di tracciamento grezzi (GPS/IMU 10Hz) vivono su S3/object
storage, referenziati da data_ref — il DB indicizza metadati/risultati, non
contiene le serie temporali riga per riga (altrimenti non scala oltre poche
sessioni).

## wind_stations
id
provider                 -- noaa_ndbc | noaa_metar | open_meteo | custom_device
external_station_id        -- es. "44013", "CSIM3", "KBOS"
name
station_type                 -- buoy | metar | forecast_grid | custom_device
lat
lng

## wind_observations
id
wind_station_id          -- FK wind_stations.id
observed_at                 -- timestamp del dato meteo
twd_deg
tws_kts
gust_kts                       -- nullable
fetched_at                       -- quando l'abbiamo scaricato dall'API (audit/cache)

nota: wind_observations è una cache locale dei dati esterni (NOAA NDBC/METAR,
Open-Meteo) o di un'eventuale stazione custom fissa al circolo — evita di
richiamare l'API a ogni render e mantiene storicità per rigiocare/ricalcolare
regate passate anche se l'API a monte ruota via i dati vecchi. observed_at è
il timestamp del dato meteo, fetched_at quando l'abbiamo scaricato. La scelta
di quale/quali wind_station aggregare per una regata/sessione resta a runtime
(algoritmo di selezione/aggregazione da valutare), non persistita come default
su regattas/race_days.