# Example queries

Run these in Supabase Studio (http://localhost:8000) or with `psql` in the database
container:

```bash
docker exec -it supabase-db psql -U postgres
```

Both have full rights. To be sure a query changes nothing, start with
`BEGIN READ ONLY;` and end with `ROLLBACK;`.

The examples use the field names of `datasets/spheroid_example.yaml`; another dataset
has the names of its own config. Useful to know:

- Every row has a `dataset`. Filter on it: two datasets can share a workbook or zip name.
- `fields` holds the values the config reads, by the config's names: `i.fields` from the
  file name, `w.fields` from the sheet. `->>` gives text, so cast numbers:
  `(i.fields ->> 'timepoint_minutes')::int`; day 2 is `2 * 1440`.
- Derived sample fields are lists. Test one value with containment:
  `w.fields -> 'treatment_norm' ? 'ibrutinib'`.
- Sheet columns that are not config fields are in `w.props`, under their original header.
- `i.experiment` is the image's group: the experiment from the sheet, or else its folder.
- `i.match_status` is `matched`, `inferred` (a key taken from the experiment),
  `unmatched` or `ambiguous`. An image can be in several zips, so check `source_zip`
  when you count images.

## 1. Annotated images with a treatment, between two days

```sql
SELECT i.original_name, i.experiment, i.fields ->> 'vid' AS vid, i.fields ->> 'well' AS well,
       (i.fields ->> 'timepoint_minutes')::int / 1440.0 AS day,
       w.fields -> 'treatment_norm' AS treatment, w.fields ->> 'concentration' AS concentration,
       w.fields ->> 'concentration_unit' AS unit,
       a.annotator_label, jsonb_array_length(a.regions) AS regions
FROM _fd.imagehub_images i
JOIN _fd.imagehub_wells w ON w.id = i.well_id
JOIN _fd.imagehub_annotations a ON a.image_id = i.id
WHERE i.dataset = 'spheroid_example'
  AND w.fields -> 'treatment_norm' ? 'ibrutinib'
  AND (i.fields ->> 'timepoint_minutes')::int BETWEEN 2 * 1440 AND 4 * 1440
ORDER BY i.experiment, vid, well, day;
```

## 2. Annotated images and regions per experiment and annotator

```sql
SELECT i.dataset, i.experiment, a.annotator_label,
       count(DISTINCT i.id) AS images,
       sum(jsonb_array_length(a.regions)) AS regions
FROM _fd.imagehub_annotations a
JOIN _fd.imagehub_images i ON i.id = a.image_id
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```

## 3. A sheet value per condition, with image and annotation counts

`Viability (%)` is one of the columns in `props`; text is converted only where it looks
like a number.

```sql
SELECT w.fields ->> 'experiment' AS experiment, w.fields -> 'treatment_norm' AS treatment,
       w.fields ->> 'concentration' AS concentration, w.fields ->> 'concentration_unit' AS unit,
       count(DISTINCT w.id) AS wells,
       round(avg((w.props ->> 'Viability (%)')::numeric)
             FILTER (WHERE w.props ->> 'Viability (%)' ~ '^-?[0-9.]+$'), 1) AS mean_viability,
       count(DISTINCT i.id) AS images,
       count(DISTINCT a.image_id) AS annotated_images
FROM _fd.imagehub_wells w
LEFT JOIN _fd.imagehub_images i ON i.well_id = w.id
LEFT JOIN _fd.imagehub_annotations a ON a.image_id = i.id
WHERE w.dataset = 'spheroid_example' AND w.props ? 'Viability (%)'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3
LIMIT 50;
```
