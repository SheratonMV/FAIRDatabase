-- Image hub plugin schema. Idempotent: re-running this file must be a no-op.

-- One row per well (one spheroid). Natural key is the source position, because
-- (vid, well) is not unique inside a sheet.
CREATE TABLE IF NOT EXISTS _fd.imagehub_wells (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         uuid NOT NULL REFERENCES auth.users(id),
    experiment       text,
    source_workbook  text NOT NULL,
    source_sheet     text NOT NULL,
    source_row       integer NOT NULL,
    vid              text,                 -- raw value: 2832, EX22, 3494;3495
    vids             text[] NOT NULL DEFAULT '{}',  -- vid split on ';'
    well             text,
    volgnummer       text,
    treatment_raw    text,
    treatment_norm   text[] NOT NULL DEFAULT '{}',
    concentration    text,                 -- raw value, not parsed to a number
    tissue           text,
    stimulation      text,
    props            jsonb NOT NULL DEFAULT '{}'::jsonb,  -- all other columns
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_workbook, source_sheet, source_row)
);

-- Sheets use different units (nM, ng/mL, ug/mL): never compare without the unit.
ALTER TABLE _fd.imagehub_wells
    ADD COLUMN IF NOT EXISTS concentration_unit text;

-- Normalised stimulation (mapping approved by the data owner).
ALTER TABLE _fd.imagehub_wells
    ADD COLUMN IF NOT EXISTS stimulation_norm text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS imagehub_wells_owner_idx
    ON _fd.imagehub_wells (owner_id);
CREATE INDEX IF NOT EXISTS imagehub_wells_experiment_well_idx
    ON _fd.imagehub_wells (experiment, well);
CREATE INDEX IF NOT EXISTS imagehub_wells_vids_idx
    ON _fd.imagehub_wells USING gin (vids);
CREATE INDEX IF NOT EXISTS imagehub_wells_treatment_idx
    ON _fd.imagehub_wells USING gin (treatment_norm);

-- One row per image file inside a zip. storage_path is set only once the file
-- has been uploaded to the bucket; preview_path holds the browser-viewable JPEG.
CREATE TABLE IF NOT EXISTS _fd.imagehub_images (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id           uuid NOT NULL REFERENCES auth.users(id),
    well_id            uuid REFERENCES _fd.imagehub_wells(id) ON DELETE SET NULL,
    match_status       text NOT NULL DEFAULT 'unmatched'
                       CHECK (match_status IN ('matched', 'inferred', 'unmatched', 'ambiguous')),
    experiment         text,
    vid                text,
    well               text,
    field              integer,
    timepoint_minutes  integer,
    channel            text,               -- e.g. Phase, from the file name
    variant            text,               -- e.g. masks, displayed, raw BF
    source_zip         text NOT NULL,
    source_member      text NOT NULL,      -- path inside the zip
    storage_path       text,
    preview_path       text,
    mime               text,
    size_bytes         bigint,
    original_name      text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_zip, source_member)
);

-- One name per channel; `channel` keeps what the file name says.
ALTER TABLE _fd.imagehub_images
    ADD COLUMN IF NOT EXISTS channel_norm text;

CREATE INDEX IF NOT EXISTS imagehub_images_owner_idx
    ON _fd.imagehub_images (owner_id);
CREATE INDEX IF NOT EXISTS imagehub_images_well_idx
    ON _fd.imagehub_images (well_id);
CREATE INDEX IF NOT EXISTS imagehub_images_lookup_idx
    ON _fd.imagehub_images (experiment, vid, well, timepoint_minutes);
CREATE INDEX IF NOT EXISTS imagehub_images_name_idx
    ON _fd.imagehub_images (original_name);

CREATE TABLE IF NOT EXISTS _fd.imagehub_annotations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id     uuid NOT NULL REFERENCES auth.users(id),
    image_id     uuid NOT NULL REFERENCES _fd.imagehub_images(id) ON DELETE CASCADE,
    annotator_label text NOT NULL,     -- initials, or 'unknown'; names in README
    source       text NOT NULL DEFAULT 'via',
    regions      jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_file  text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (image_id, annotator_label, source_file)
);

CREATE INDEX IF NOT EXISTS imagehub_annotations_owner_idx
    ON _fd.imagehub_annotations (owner_id);

-- Legend sheets: column explanations, kept as documentation, not imported as wells.
CREATE TABLE IF NOT EXISTS _fd.imagehub_legends (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         uuid NOT NULL REFERENCES auth.users(id),
    source_workbook  text NOT NULL,
    source_sheet     text NOT NULL,
    rows             jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_workbook, source_sheet)
);

CREATE INDEX IF NOT EXISTS imagehub_legends_owner_idx
    ON _fd.imagehub_legends (owner_id);

-- Audit of exports: who exported what.
CREATE TABLE IF NOT EXISTS _fd.imagehub_exports (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id    uuid NOT NULL REFERENCES auth.users(id),
    filter      jsonb NOT NULL DEFAULT '{}'::jsonb,
    n_files     integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE _fd.imagehub_exports
    ADD COLUMN IF NOT EXISTS file_name text,
    ADD COLUMN IF NOT EXISTS size_bytes bigint,
    ADD COLUMN IF NOT EXISTS missing jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS imagehub_exports_owner_idx
    ON _fd.imagehub_exports (owner_id);

-- The original VIA file in the bucket; several annotations can point to one file.
ALTER TABLE _fd.imagehub_annotations
    ADD COLUMN IF NOT EXISTS source_storage_path text;

-- Upgrades of databases created before these columns and values existed.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = '_fd' AND table_name = 'imagehub_annotations'
                 AND column_name = 'annotator') THEN
        ALTER TABLE _fd.imagehub_annotations RENAME COLUMN annotator TO annotator_label;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'imagehub_images_match_status_check'
                     AND pg_get_constraintdef(oid) LIKE '%inferred%') THEN
        ALTER TABLE _fd.imagehub_images
            DROP CONSTRAINT IF EXISTS imagehub_images_match_status_check;
        ALTER TABLE _fd.imagehub_images
            ADD CONSTRAINT imagehub_images_match_status_check
            CHECK (match_status IN ('matched', 'inferred', 'unmatched', 'ambiguous'));
    END IF;
END $$;
