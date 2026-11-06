-- Datasets: every sample, image and legend belongs to one dataset config
-- (datasets/*.yaml). Idempotent: re-running this file must be a no-op.
--
-- `fields` holds a row's values by the names its dataset config gives them, so
-- a dataset with other columns needs no new table columns. The typed columns
-- from 001 are kept as legacy and nothing writes them any more; the backfill
-- below only copies their values into fields for rows that existed before datasets.

ALTER TABLE _fd.imagehub_wells
    ADD COLUMN IF NOT EXISTS dataset text,
    ADD COLUMN IF NOT EXISTS fields jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE _fd.imagehub_images
    ADD COLUMN IF NOT EXISTS dataset text,
    ADD COLUMN IF NOT EXISTS fields jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE _fd.imagehub_legends
    ADD COLUMN IF NOT EXISTS dataset text;

-- Rows from before datasets existed: their fields come from the typed columns,
-- and they all belong to the first dataset.
UPDATE _fd.imagehub_wells SET fields = jsonb_strip_nulls(jsonb_build_object(
    'experiment', experiment, 'vid', vid, 'vids', to_jsonb(vids), 'well', well,
    'volgnummer', volgnummer, 'treatment_raw', treatment_raw,
    'treatment_norm', to_jsonb(treatment_norm), 'concentration', concentration,
    'concentration_unit', concentration_unit, 'tissue', tissue,
    'stimulation', stimulation, 'stimulation_norm', to_jsonb(stimulation_norm)
)) WHERE dataset IS NULL;
UPDATE _fd.imagehub_images SET fields = jsonb_strip_nulls(jsonb_build_object(
    'vid', vid, 'well', well, 'field', field, 'timepoint_minutes', timepoint_minutes,
    'channel', channel, 'channel_norm', channel_norm, 'variant', variant
)) WHERE dataset IS NULL;
UPDATE _fd.imagehub_wells   SET dataset = 'spheroid_cll' WHERE dataset IS NULL;
UPDATE _fd.imagehub_images  SET dataset = 'spheroid_cll' WHERE dataset IS NULL;
UPDATE _fd.imagehub_legends SET dataset = 'spheroid_cll' WHERE dataset IS NULL;

ALTER TABLE _fd.imagehub_wells    ALTER COLUMN dataset SET NOT NULL;
ALTER TABLE _fd.imagehub_images   ALTER COLUMN dataset SET NOT NULL;
ALTER TABLE _fd.imagehub_legends  ALTER COLUMN dataset SET NOT NULL;

-- Natural keys per dataset: two datasets may have a workbook or zip of the same name.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'imagehub_wells_dataset_source_key') THEN
        ALTER TABLE _fd.imagehub_wells
            DROP CONSTRAINT IF EXISTS imagehub_wells_source_workbook_source_sheet_source_row_key;
        ALTER TABLE _fd.imagehub_wells ADD CONSTRAINT imagehub_wells_dataset_source_key
            UNIQUE (dataset, source_workbook, source_sheet, source_row);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'imagehub_images_dataset_source_key') THEN
        ALTER TABLE _fd.imagehub_images
            DROP CONSTRAINT IF EXISTS imagehub_images_source_zip_source_member_key;
        ALTER TABLE _fd.imagehub_images ADD CONSTRAINT imagehub_images_dataset_source_key
            UNIQUE (dataset, source_zip, source_member);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'imagehub_legends_dataset_source_key') THEN
        ALTER TABLE _fd.imagehub_legends
            DROP CONSTRAINT IF EXISTS imagehub_legends_source_workbook_source_sheet_key;
        ALTER TABLE _fd.imagehub_legends ADD CONSTRAINT imagehub_legends_dataset_source_key
            UNIQUE (dataset, source_workbook, source_sheet);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS imagehub_wells_fields_idx
    ON _fd.imagehub_wells USING gin (fields);
CREATE INDEX IF NOT EXISTS imagehub_images_fields_idx
    ON _fd.imagehub_images USING gin (fields);
CREATE INDEX IF NOT EXISTS imagehub_images_dataset_name_idx
    ON _fd.imagehub_images (dataset, original_name);
