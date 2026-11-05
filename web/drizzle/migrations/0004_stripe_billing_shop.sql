CREATE TABLE public.billing_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE CHECK (code IN ('plus','family','lab')),
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  is_active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.billing_prices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES public.billing_plans(id) ON DELETE CASCADE,
  billing_interval text NOT NULL CHECK (billing_interval IN ('month','year')),
  unit_amount integer CHECK (unit_amount IS NULL OR unit_amount > 0),
  currency text NOT NULL DEFAULT 'eur',
  is_active boolean NOT NULL DEFAULT false,
  stripe_price_id text,
  stripe_price_amount integer,
  UNIQUE (plan_id, billing_interval)
);
CREATE TABLE public.shop_products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  description text NOT NULL DEFAULT '',
  kind text NOT NULL CHECK (kind IN ('buddy','kit')),
  unit_amount integer CHECK (unit_amount IS NULL OR unit_amount > 0),
  currency text NOT NULL DEFAULT 'eur',
  stock integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
  is_active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.shop_orders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  customer_name text NOT NULL,
  customer_email text NOT NULL,
  shipping jsonb,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','paid','expired','failed')),
  total_amount integer NOT NULL,
  currency text NOT NULL,
  request_key uuid NOT NULL UNIQUE,
  stripe_session_id text UNIQUE,
  stripe_payment_intent text,
  stock_released boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  paid_at timestamptz
);
CREATE TABLE public.shop_order_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id uuid NOT NULL REFERENCES public.shop_orders(id) ON DELETE CASCADE,
  product_id uuid NOT NULL REFERENCES public.shop_products(id),
  product_name text NOT NULL,
  quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 10),
  unit_amount integer NOT NULL
);
CREATE TABLE public.billing_customers (
  user_id uuid PRIMARY KEY,
  stripe_customer_id text NOT NULL UNIQUE
);
CREATE TABLE public.billing_subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  stripe_subscription_id text NOT NULL UNIQUE,
  stripe_customer_id text NOT NULL,
  plan_code text NOT NULL,
  billing_interval text NOT NULL,
  status text NOT NULL,
  current_period_end timestamptz,
  cancel_at_period_end boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON public.billing_subscriptions(user_id);
CREATE TABLE public.billing_checkout_locks (
  user_id uuid PRIMARY KEY,
  stripe_session_id text NOT NULL,
  expires_at timestamptz NOT NULL
);
CREATE TABLE public.stripe_events (
  id text PRIMARY KEY,
  type text NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON public.billing_plans, public.billing_prices, public.shop_products TO anon, authenticated;
GRANT SELECT ON public.shop_orders, public.shop_order_items, public.billing_subscriptions TO authenticated;
GRANT ALL ON public.billing_plans, public.billing_prices, public.shop_products, public.shop_orders, public.shop_order_items, public.billing_customers, public.billing_subscriptions, public.billing_checkout_locks, public.stripe_events TO service_role;

ALTER TABLE public.billing_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shop_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shop_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shop_order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.billing_checkout_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stripe_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public reads plans" ON public.billing_plans FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public reads prices" ON public.billing_prices FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Public reads products" ON public.shop_products FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Owners read orders" ON public.shop_orders FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY "Owners read order items" ON public.shop_order_items FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.shop_orders o WHERE o.id = order_id AND o.user_id = auth.uid()));
CREATE POLICY "Owners read subscriptions" ON public.billing_subscriptions FOR SELECT TO authenticated USING (user_id = auth.uid());

REVOKE SELECT (stripe_price_id, stripe_price_amount) ON public.billing_prices FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.reserve_stock(p_items jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE it jsonb; n integer;
BEGIN
  FOR it IN SELECT * FROM jsonb_array_elements(p_items) LOOP
    UPDATE shop_products SET stock = stock - (it->>'quantity')::int
      WHERE id = (it->>'product_id')::uuid AND is_active AND stock >= (it->>'quantity')::int;
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n = 0 THEN RAISE EXCEPTION 'out_of_stock'; END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE OR REPLACE FUNCTION public.release_order_stock(p_order uuid)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  UPDATE shop_orders SET stock_released = true WHERE id = p_order AND NOT stock_released AND status <> 'paid';
  IF FOUND THEN
    UPDATE shop_products p SET stock = p.stock + i.quantity FROM shop_order_items i WHERE i.order_id = p_order AND i.product_id = p.id;
  END IF;
END $$;
REVOKE ALL ON FUNCTION public.reserve_stock(jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.release_order_stock(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_stock(jsonb), public.release_order_stock(uuid) TO service_role;

INSERT INTO public.billing_plans (code, name, description) VALUES
 ('plus','Peluqo Plus','Más lecciones y tutor ampliado.'),
 ('family','Peluqo Family','Varios perfiles para toda la familia.'),
 ('lab','Peluqo Lab','Itinerarios de robótica y creación.');
INSERT INTO public.billing_prices (plan_id, billing_interval) SELECT id, i FROM public.billing_plans, unnest(ARRAY['month','year']) i;
INSERT INTO public.shop_products (slug, name, description, kind) VALUES
 ('peluqo-buddy','Peluqo Buddy','El compañero físico de aprendizaje.','buddy'),
 ('kit-inicial','Kit DIY inicial','Monta tu Peluqo paso a paso.','kit'),
 ('kit-sensores','Kit DIY sensores','Sensores y emociones para tu Peluqo.','kit');