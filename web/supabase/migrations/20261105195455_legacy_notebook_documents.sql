INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'learner-documents', 'learner-documents', false, 10485760,
  ARRAY['application/pdf', 'text/plain', 'application/octet-stream']
)
ON CONFLICT (id) DO NOTHING;

CREATE FUNCTION public.owns_notebook_upload(p_path text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF auth.uid() IS NULL OR split_part(p_path, '/', 1) <> auth.uid()::text THEN RETURN false; END IF;
  PERFORM 1 FROM public.notebooks n
    WHERE n.id::text = split_part(p_path, '/', 2) AND n.owner_user_id = auth.uid()
    FOR KEY SHARE;
  RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION public.owns_notebook_upload(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.owns_notebook_upload(text) TO authenticated;

DROP POLICY IF EXISTS own_document_files ON storage.objects;
CREATE POLICY notebook_file_read ON storage.objects FOR SELECT TO authenticated
USING (bucket_id = 'learner-documents' AND (storage.foldername(name))[1] = (SELECT auth.uid())::text);
CREATE POLICY notebook_file_delete ON storage.objects FOR DELETE TO authenticated
USING (bucket_id = 'learner-documents' AND (storage.foldername(name))[1] = (SELECT auth.uid())::text);
CREATE POLICY notebook_file_create ON storage.objects FOR INSERT TO authenticated
WITH CHECK (
  bucket_id = 'learner-documents'
  AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
  AND name ~* '/[^/]+\.(pdf|txt)$'
  AND public.owns_notebook_upload(name)
);

GRANT INSERT, UPDATE ON public.notebook_documents TO authenticated;
GRANT INSERT, DELETE ON public.document_chunks TO authenticated;

CREATE POLICY insert_own_notebook_documents ON public.notebook_documents FOR INSERT TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.notebooks n
    WHERE n.id = notebook_id AND n.owner_user_id = (SELECT auth.uid())
      AND storage_path LIKE n.owner_user_id::text || '/' || n.id::text || '/%'
  )
);
CREATE POLICY update_own_notebook_documents ON public.notebook_documents FOR UPDATE TO authenticated
USING (
  EXISTS (SELECT 1 FROM public.notebooks n WHERE n.id = notebook_id AND n.owner_user_id = (SELECT auth.uid()))
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.notebooks n
    WHERE n.id = notebook_id AND n.owner_user_id = (SELECT auth.uid())
      AND storage_path LIKE n.owner_user_id::text || '/' || n.id::text || '/%'
  )
);
CREATE POLICY delete_own_document_chunks ON public.document_chunks FOR DELETE TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.notebook_documents d JOIN public.notebooks n ON n.id = d.notebook_id
    WHERE d.id = document_id AND n.owner_user_id = (SELECT auth.uid())
  )
);
CREATE POLICY insert_own_document_chunks ON public.document_chunks FOR INSERT TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM public.notebook_documents d JOIN public.notebooks n ON n.id = d.notebook_id
    WHERE d.id = document_id AND n.owner_user_id = (SELECT auth.uid())
  )
);
CREATE FUNCTION public.finalize_notebook_document(
  p_notebook uuid, p_path text, p_name text, p_size bigint, p_mime text,
  p_chunks jsonb, p_error text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_document public.notebook_documents;
BEGIN
  IF auth.uid() IS NULL THEN RAISE EXCEPTION 'Inicia sesión'; END IF;
  PERFORM 1 FROM public.notebooks n
    WHERE n.id = p_notebook AND n.owner_user_id = auth.uid() FOR KEY SHARE;
  IF NOT FOUND OR p_path IS NULL
    OR p_path NOT LIKE auth.uid()::text || '/' || p_notebook::text || '/%'
    OR NOT EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id = 'learner-documents' AND name = p_path)
  THEN RAISE EXCEPTION 'Documento no autorizado'; END IF;
  IF p_name IS NULL OR length(p_name) NOT BETWEEN 1 AND 150
    OR p_size IS NULL OR p_size NOT BETWEEN 1 AND 10485760
    OR p_mime IS NULL OR p_mime NOT IN ('application/pdf', 'text/plain')
    OR p_chunks IS NULL OR jsonb_typeof(p_chunks) <> 'array'
    OR jsonb_array_length(p_chunks) > 400
    OR (p_error IS NOT NULL AND (length(p_error) NOT BETWEEN 1 AND 500 OR jsonb_array_length(p_chunks) <> 0))
    OR (p_error IS NULL AND jsonb_array_length(p_chunks) = 0)
  THEN RAISE EXCEPTION 'Documento no válido'; END IF;
  IF EXISTS (
    SELECT 1 FROM jsonb_array_elements(p_chunks) piece
    WHERE jsonb_typeof(piece->'content') IS DISTINCT FROM 'string'
      OR length(piece->>'content') NOT BETWEEN 1 AND 1400
      OR (piece->>'page_number' IS NOT NULL AND (piece->>'page_number')::integer NOT BETWEEN 1 AND 100)
  ) OR (
    SELECT coalesce(sum(length(piece->>'content')), 0) FROM jsonb_array_elements(p_chunks) piece
  ) > 400000 THEN RAISE EXCEPTION 'Texto no válido'; END IF;

  INSERT INTO public.notebook_documents (notebook_id, storage_path, file_name, file_size, mime_type)
    VALUES (p_notebook, p_path, p_name, p_size, p_mime)
    ON CONFLICT (storage_path) DO NOTHING;
  SELECT * INTO v_document FROM public.notebook_documents WHERE storage_path = p_path FOR UPDATE;
  IF NOT FOUND OR v_document.notebook_id <> p_notebook THEN RAISE EXCEPTION 'Documento no autorizado'; END IF;
  IF v_document.processing_status = 'ready' THEN
    RETURN jsonb_build_object('ok', true, 'id', v_document.id, 'error', NULL);
  END IF;

  DELETE FROM public.document_chunks WHERE document_id = v_document.id;
  INSERT INTO public.document_chunks (document_id, chunk_index, content, page_number)
    SELECT v_document.id, (piece.ordinality - 1)::integer, piece.value->>'content',
      (piece.value->>'page_number')::integer
    FROM jsonb_array_elements(p_chunks) WITH ORDINALITY AS piece(value, ordinality);
  UPDATE public.notebook_documents
    SET processing_status = CASE WHEN p_error IS NULL THEN 'ready' ELSE 'error' END,
      processing_error = p_error
    WHERE id = v_document.id;
  RETURN jsonb_build_object('ok', p_error IS NULL, 'id', v_document.id, 'error', p_error);
END $$;
REVOKE ALL ON FUNCTION public.finalize_notebook_document(uuid, text, text, bigint, text, jsonb, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.finalize_notebook_document(uuid, text, text, bigint, text, jsonb, text) TO authenticated;
