-- Photo Scene Builder v0.5: permit private worker JSON results.
-- The original bucket accepted images only, so successful detection failed at upload.

update storage.buckets
set allowed_mime_types = case
  when allowed_mime_types is null then array['image/jpeg', 'image/png', 'image/webp', 'application/json']::text[]
  when 'application/json' = any(allowed_mime_types) then allowed_mime_types
  else array_append(allowed_mime_types, 'application/json')
end
where id = 'analysis-scenes';

do $$
begin
  if not exists (
    select 1 from storage.buckets
    where id = 'analysis-scenes'
      and public = false
      and 'application/json' = any(allowed_mime_types)
  ) then
    raise exception 'analysis-scenes bucket is missing, public, or does not allow application/json';
  end if;
end;
$$;

notify pgrst, 'reload schema';
