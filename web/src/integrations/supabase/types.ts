export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.18";
  };
  public: {
    Tables: {
      achievements: {
        Row: {
          description: string;
          icon: string;
          id: string;
          lesson_id: string | null;
          title: string;
        };
        Insert: {
          description?: string;
          icon?: string;
          id?: string;
          lesson_id?: string | null;
          title: string;
        };
        Update: {
          description?: string;
          icon?: string;
          id?: string;
          lesson_id?: string | null;
          title?: string;
        };
        Relationships: [
          {
            foreignKeyName: "achievements_lesson_id_fkey";
            columns: ["lesson_id"];
            isOneToOne: true;
            referencedRelation: "lessons";
            referencedColumns: ["id"];
          },
        ];
      };
      activities: {
        Row: {
          activity_type: string;
          display_order: number;
          id: string;
          instructions: string;
          lesson_id: string;
          points: number;
          public_config: Json;
          title: string;
        };
        Insert: {
          activity_type: string;
          display_order?: number;
          id?: string;
          instructions?: string;
          lesson_id: string;
          points?: number;
          public_config?: Json;
          title: string;
        };
        Update: {
          activity_type?: string;
          display_order?: number;
          id?: string;
          instructions?: string;
          lesson_id?: string;
          points?: number;
          public_config?: Json;
          title?: string;
        };
        Relationships: [
          {
            foreignKeyName: "activities_lesson_id_fkey";
            columns: ["lesson_id"];
            isOneToOne: false;
            referencedRelation: "lessons";
            referencedColumns: ["id"];
          },
        ];
      };
      activity_attempts: {
        Row: {
          activity_id: string;
          created_at: string;
          feedback: Json;
          id: string;
          is_correct: boolean;
          learner_id: string;
          score: number;
          submitted_answer: Json;
        };
        Insert: {
          activity_id: string;
          created_at?: string;
          feedback?: Json;
          id?: string;
          is_correct: boolean;
          learner_id: string;
          score: number;
          submitted_answer: Json;
        };
        Update: {
          activity_id?: string;
          created_at?: string;
          feedback?: Json;
          id?: string;
          is_correct?: boolean;
          learner_id?: string;
          score?: number;
          submitted_answer?: Json;
        };
        Relationships: [
          {
            foreignKeyName: "activity_attempts_activity_id_fkey";
            columns: ["activity_id"];
            isOneToOne: false;
            referencedRelation: "activities";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "activity_attempts_learner_id_fkey";
            columns: ["learner_id"];
            isOneToOne: false;
            referencedRelation: "learners";
            referencedColumns: ["id"];
          },
        ];
      };
      activity_solutions: {
        Row: {
          activity_id: string;
          answer_config: Json;
          explanation: string;
        };
        Insert: {
          activity_id: string;
          answer_config: Json;
          explanation: string;
        };
        Update: {
          activity_id?: string;
          answer_config?: Json;
          explanation?: string;
        };
        Relationships: [
          {
            foreignKeyName: "activity_solutions_activity_id_fkey";
            columns: ["activity_id"];
            isOneToOne: true;
            referencedRelation: "activities";
            referencedColumns: ["id"];
          },
        ];
      };
      ai_access_state: {
        Row: {
          id: string;
          kind: string;
          paused: boolean;
          reason: string;
          updated_at: string;
        };
        Insert: {
          id: string;
          kind?: string;
          paused?: boolean;
          reason?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          kind?: string;
          paused?: boolean;
          reason?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      ai_messages: {
        Row: {
          content: string;
          created_at: string;
          id: string;
          notebook_id: string;
          role: string;
          source_references: Json;
        };
        Insert: {
          content: string;
          created_at?: string;
          id?: string;
          notebook_id: string;
          role: string;
          source_references?: Json;
        };
        Update: {
          content?: string;
          created_at?: string;
          id?: string;
          notebook_id?: string;
          role?: string;
          source_references?: Json;
        };
        Relationships: [
          {
            foreignKeyName: "ai_messages_notebook_id_fkey";
            columns: ["notebook_id"];
            isOneToOne: false;
            referencedRelation: "notebooks";
            referencedColumns: ["id"];
          },
        ];
      };
      ai_usage: {
        Row: {
          created_at: string;
          id: string;
          user_id: string;
        };
        Insert: {
          created_at?: string;
          id?: string;
          user_id: string;
        };
        Update: {
          created_at?: string;
          id?: string;
          user_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "ai_usage_user_id_fkey";
            columns: ["user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      billing_checkout_locks: {
        Row: {
          expires_at: string;
          stripe_session_id: string;
          user_id: string;
        };
        Insert: {
          expires_at: string;
          stripe_session_id: string;
          user_id: string;
        };
        Update: {
          expires_at?: string;
          stripe_session_id?: string;
          user_id?: string;
        };
        Relationships: [];
      };
      billing_customers: {
        Row: {
          stripe_customer_id: string;
          user_id: string;
        };
        Insert: {
          stripe_customer_id: string;
          user_id: string;
        };
        Update: {
          stripe_customer_id?: string;
          user_id?: string;
        };
        Relationships: [];
      };
      billing_plans: {
        Row: {
          code: string;
          created_at: string;
          description: string;
          id: string;
          is_active: boolean;
          name: string;
        };
        Insert: {
          code: string;
          created_at?: string;
          description?: string;
          id?: string;
          is_active?: boolean;
          name: string;
        };
        Update: {
          code?: string;
          created_at?: string;
          description?: string;
          id?: string;
          is_active?: boolean;
          name?: string;
        };
        Relationships: [];
      };
      billing_prices: {
        Row: {
          billing_interval: string;
          currency: string;
          id: string;
          is_active: boolean;
          plan_id: string;
          stripe_price_amount: number | null;
          stripe_price_id: string | null;
          unit_amount: number | null;
        };
        Insert: {
          billing_interval: string;
          currency?: string;
          id?: string;
          is_active?: boolean;
          plan_id: string;
          stripe_price_amount?: number | null;
          stripe_price_id?: string | null;
          unit_amount?: number | null;
        };
        Update: {
          billing_interval?: string;
          currency?: string;
          id?: string;
          is_active?: boolean;
          plan_id?: string;
          stripe_price_amount?: number | null;
          stripe_price_id?: string | null;
          unit_amount?: number | null;
        };
        Relationships: [
          {
            foreignKeyName: "billing_prices_plan_id_fkey";
            columns: ["plan_id"];
            isOneToOne: false;
            referencedRelation: "billing_plans";
            referencedColumns: ["id"];
          },
        ];
      };
      billing_subscriptions: {
        Row: {
          billing_interval: string;
          cancel_at_period_end: boolean;
          confirmation_code: string | null;
          confirmation_email_sent_at: string | null;
          current_period_end: string | null;
          id: string;
          plan_code: string;
          status: string;
          stripe_customer_id: string;
          stripe_subscription_id: string;
          updated_at: string;
          user_id: string;
        };
        Insert: {
          billing_interval: string;
          cancel_at_period_end?: boolean;
          confirmation_code?: string | null;
          confirmation_email_sent_at?: string | null;
          current_period_end?: string | null;
          id?: string;
          plan_code: string;
          status: string;
          stripe_customer_id: string;
          stripe_subscription_id: string;
          updated_at?: string;
          user_id: string;
        };
        Update: {
          billing_interval?: string;
          cancel_at_period_end?: boolean;
          confirmation_code?: string | null;
          confirmation_email_sent_at?: string | null;
          current_period_end?: string | null;
          id?: string;
          plan_code?: string;
          status?: string;
          stripe_customer_id?: string;
          stripe_subscription_id?: string;
          updated_at?: string;
          user_id?: string;
        };
        Relationships: [];
      };
      device_events: {
        Row: {
          created_at: string;
          device_id: string;
          event_type: string;
          id: string;
          payload: Json;
        };
        Insert: {
          created_at?: string;
          device_id: string;
          event_type: string;
          id?: string;
          payload?: Json;
        };
        Update: {
          created_at?: string;
          device_id?: string;
          event_type?: string;
          id?: string;
          payload?: Json;
        };
        Relationships: [
          {
            foreignKeyName: "device_events_device_id_fkey";
            columns: ["device_id"];
            isOneToOne: false;
            referencedRelation: "devices";
            referencedColumns: ["id"];
          },
        ];
      };
      device_pairing_requests: {
        Row: {
          code_hash: string;
          consumed_at: string | null;
          created_at: string;
          expires_at: string;
          id: string;
          owner_user_id: string;
        };
        Insert: {
          code_hash: string;
          consumed_at?: string | null;
          created_at?: string;
          expires_at: string;
          id?: string;
          owner_user_id: string;
        };
        Update: {
          code_hash?: string;
          consumed_at?: string | null;
          created_at?: string;
          expires_at?: string;
          id?: string;
          owner_user_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "device_pairing_requests_owner_user_id_fkey";
            columns: ["owner_user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      devices: {
        Row: {
          created_at: string;
          device_uid: string;
          firmware_version: string | null;
          id: string;
          last_seen_at: string | null;
          learner_id: string | null;
          name: string;
          owner_user_id: string;
          status: string;
        };
        Insert: {
          created_at?: string;
          device_uid: string;
          firmware_version?: string | null;
          id?: string;
          last_seen_at?: string | null;
          learner_id?: string | null;
          name: string;
          owner_user_id: string;
          status?: string;
        };
        Update: {
          created_at?: string;
          device_uid?: string;
          firmware_version?: string | null;
          id?: string;
          last_seen_at?: string | null;
          learner_id?: string | null;
          name?: string;
          owner_user_id?: string;
          status?: string;
        };
        Relationships: [
          {
            foreignKeyName: "devices_learner_id_fkey";
            columns: ["learner_id"];
            isOneToOne: false;
            referencedRelation: "learners";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "devices_owner_user_id_fkey";
            columns: ["owner_user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      document_chunks: {
        Row: {
          chunk_index: number;
          content: string;
          document_id: string;
          id: string;
          page_number: number | null;
        };
        Insert: {
          chunk_index: number;
          content: string;
          document_id: string;
          id?: string;
          page_number?: number | null;
        };
        Update: {
          chunk_index?: number;
          content?: string;
          document_id?: string;
          id?: string;
          page_number?: number | null;
        };
        Relationships: [
          {
            foreignKeyName: "document_chunks_document_id_fkey";
            columns: ["document_id"];
            isOneToOne: false;
            referencedRelation: "notebook_documents";
            referencedColumns: ["id"];
          },
        ];
      };
      learner_achievements: {
        Row: {
          achievement_id: string;
          earned_at: string;
          id: string;
          learner_id: string;
        };
        Insert: {
          achievement_id: string;
          earned_at?: string;
          id?: string;
          learner_id: string;
        };
        Update: {
          achievement_id?: string;
          earned_at?: string;
          id?: string;
          learner_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "learner_achievements_achievement_id_fkey";
            columns: ["achievement_id"];
            isOneToOne: false;
            referencedRelation: "achievements";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "learner_achievements_learner_id_fkey";
            columns: ["learner_id"];
            isOneToOne: false;
            referencedRelation: "learners";
            referencedColumns: ["id"];
          },
        ];
      };
      learners: {
        Row: {
          age_band: string;
          avatar_config: Json;
          created_at: string;
          display_name: string;
          education_level: string;
          grade_level: string;
          id: string;
          owner_user_id: string;
          preferences: Json;
        };
        Insert: {
          age_band?: string;
          avatar_config?: Json;
          created_at?: string;
          display_name: string;
          education_level?: string;
          grade_level?: string;
          id?: string;
          owner_user_id: string;
          preferences?: Json;
        };
        Update: {
          age_band?: string;
          avatar_config?: Json;
          created_at?: string;
          display_name?: string;
          education_level?: string;
          grade_level?: string;
          id?: string;
          owner_user_id?: string;
          preferences?: Json;
        };
        Relationships: [
          {
            foreignKeyName: "learners_owner_user_id_fkey";
            columns: ["owner_user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      lesson_progress: {
        Row: {
          best_score: number;
          completed_at: string | null;
          completion_percentage: number;
          id: string;
          learner_id: string;
          lesson_id: string;
          status: string;
          updated_at: string;
        };
        Insert: {
          best_score?: number;
          completed_at?: string | null;
          completion_percentage?: number;
          id?: string;
          learner_id: string;
          lesson_id: string;
          status?: string;
          updated_at?: string;
        };
        Update: {
          best_score?: number;
          completed_at?: string | null;
          completion_percentage?: number;
          id?: string;
          learner_id?: string;
          lesson_id?: string;
          status?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "lesson_progress_learner_id_fkey";
            columns: ["learner_id"];
            isOneToOne: false;
            referencedRelation: "learners";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "lesson_progress_lesson_id_fkey";
            columns: ["lesson_id"];
            isOneToOne: false;
            referencedRelation: "lessons";
            referencedColumns: ["id"];
          },
        ];
      };
      lessons: {
        Row: {
          content: Json;
          cover_image: string | null;
          created_at: string;
          description: string;
          education_level: string;
          estimated_minutes: number;
          id: string;
          slug: string;
          status: string;
          title: string;
          topic_id: string;
          updated_at: string;
        };
        Insert: {
          content?: Json;
          cover_image?: string | null;
          created_at?: string;
          description?: string;
          education_level?: string;
          estimated_minutes?: number;
          id?: string;
          slug: string;
          status?: string;
          title: string;
          topic_id: string;
          updated_at?: string;
        };
        Update: {
          content?: Json;
          cover_image?: string | null;
          created_at?: string;
          description?: string;
          education_level?: string;
          estimated_minutes?: number;
          id?: string;
          slug?: string;
          status?: string;
          title?: string;
          topic_id?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "lessons_topic_id_fkey";
            columns: ["topic_id"];
            isOneToOne: false;
            referencedRelation: "topics";
            referencedColumns: ["id"];
          },
        ];
      };
      notebook_documents: {
        Row: {
          file_name: string;
          file_size: number;
          id: string;
          mime_type: string;
          notebook_id: string;
          processing_error: string | null;
          processing_status: string;
          storage_path: string;
          uploaded_at: string;
        };
        Insert: {
          file_name: string;
          file_size: number;
          id?: string;
          mime_type: string;
          notebook_id: string;
          processing_error?: string | null;
          processing_status?: string;
          storage_path: string;
          uploaded_at?: string;
        };
        Update: {
          file_name?: string;
          file_size?: number;
          id?: string;
          mime_type?: string;
          notebook_id?: string;
          processing_error?: string | null;
          processing_status?: string;
          storage_path?: string;
          uploaded_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "notebook_documents_notebook_id_fkey";
            columns: ["notebook_id"];
            isOneToOne: false;
            referencedRelation: "notebooks";
            referencedColumns: ["id"];
          },
        ];
      };
      notebooks: {
        Row: {
          created_at: string;
          description: string;
          id: string;
          learner_id: string;
          owner_user_id: string;
          title: string;
        };
        Insert: {
          created_at?: string;
          description?: string;
          id?: string;
          learner_id: string;
          owner_user_id: string;
          title: string;
        };
        Update: {
          created_at?: string;
          description?: string;
          id?: string;
          learner_id?: string;
          owner_user_id?: string;
          title?: string;
        };
        Relationships: [
          {
            foreignKeyName: "notebooks_learner_id_fkey";
            columns: ["learner_id"];
            isOneToOne: false;
            referencedRelation: "learners";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "notebooks_owner_user_id_fkey";
            columns: ["owner_user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      profiles: {
        Row: {
          account_type: string;
          active_learner_id: string | null;
          age_band: string;
          created_at: string;
          display_name: string;
          id: string;
          updated_at: string;
        };
        Insert: {
          account_type?: string;
          active_learner_id?: string | null;
          age_band?: string;
          created_at?: string;
          display_name?: string;
          id: string;
          updated_at?: string;
        };
        Update: {
          account_type?: string;
          active_learner_id?: string | null;
          age_band?: string;
          created_at?: string;
          display_name?: string;
          id?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      shop_order_items: {
        Row: {
          id: string;
          order_id: string;
          product_id: string;
          product_name: string;
          quantity: number;
          unit_amount: number;
        };
        Insert: {
          id?: string;
          order_id: string;
          product_id: string;
          product_name: string;
          quantity: number;
          unit_amount: number;
        };
        Update: {
          id?: string;
          order_id?: string;
          product_id?: string;
          product_name?: string;
          quantity?: number;
          unit_amount?: number;
        };
        Relationships: [
          {
            foreignKeyName: "shop_order_items_order_id_fkey";
            columns: ["order_id"];
            isOneToOne: false;
            referencedRelation: "shop_orders";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "shop_order_items_product_id_fkey";
            columns: ["product_id"];
            isOneToOne: false;
            referencedRelation: "shop_products";
            referencedColumns: ["id"];
          },
        ];
      };
      shop_orders: {
        Row: {
          confirmation_code: string | null;
          confirmation_email_sent_at: string | null;
          created_at: string;
          currency: string;
          customer_email: string;
          customer_name: string;
          id: string;
          paid_at: string | null;
          request_key: string;
          shipping: Json | null;
          status: string;
          stock_released: boolean;
          stripe_payment_intent: string | null;
          stripe_session_id: string | null;
          total_amount: number;
          user_id: string | null;
        };
        Insert: {
          confirmation_code?: string | null;
          confirmation_email_sent_at?: string | null;
          created_at?: string;
          currency: string;
          customer_email: string;
          customer_name: string;
          id?: string;
          paid_at?: string | null;
          request_key: string;
          shipping?: Json | null;
          status?: string;
          stock_released?: boolean;
          stripe_payment_intent?: string | null;
          stripe_session_id?: string | null;
          total_amount: number;
          user_id?: string | null;
        };
        Update: {
          confirmation_code?: string | null;
          confirmation_email_sent_at?: string | null;
          created_at?: string;
          currency?: string;
          customer_email?: string;
          customer_name?: string;
          id?: string;
          paid_at?: string | null;
          request_key?: string;
          shipping?: Json | null;
          status?: string;
          stock_released?: boolean;
          stripe_payment_intent?: string | null;
          stripe_session_id?: string | null;
          total_amount?: number;
          user_id?: string | null;
        };
        Relationships: [];
      };
      shop_products: {
        Row: {
          created_at: string;
          currency: string;
          description: string;
          id: string;
          is_active: boolean;
          kind: string;
          name: string;
          slug: string;
          stock: number;
          unit_amount: number | null;
        };
        Insert: {
          created_at?: string;
          currency?: string;
          description?: string;
          id?: string;
          is_active?: boolean;
          kind: string;
          name: string;
          slug: string;
          stock?: number;
          unit_amount?: number | null;
        };
        Update: {
          created_at?: string;
          currency?: string;
          description?: string;
          id?: string;
          is_active?: boolean;
          kind?: string;
          name?: string;
          slug?: string;
          stock?: number;
          unit_amount?: number | null;
        };
        Relationships: [];
      };
      stripe_events: {
        Row: {
          id: string;
          received_at: string;
          type: string;
        };
        Insert: {
          id: string;
          received_at?: string;
          type: string;
        };
        Update: {
          id?: string;
          received_at?: string;
          type?: string;
        };
        Relationships: [];
      };
      subjects: {
        Row: {
          color: string;
          description: string;
          display_order: number;
          id: string;
          is_active: boolean;
          name: string;
          slug: string;
        };
        Insert: {
          color?: string;
          description?: string;
          display_order?: number;
          id?: string;
          is_active?: boolean;
          name: string;
          slug: string;
        };
        Update: {
          color?: string;
          description?: string;
          display_order?: number;
          id?: string;
          is_active?: boolean;
          name?: string;
          slug?: string;
        };
        Relationships: [];
      };
      topics: {
        Row: {
          description: string;
          display_order: number;
          id: string;
          slug: string;
          subject_id: string;
          title: string;
        };
        Insert: {
          description?: string;
          display_order?: number;
          id?: string;
          slug: string;
          subject_id: string;
          title: string;
        };
        Update: {
          description?: string;
          display_order?: number;
          id?: string;
          slug?: string;
          subject_id?: string;
          title?: string;
        };
        Relationships: [
          {
            foreignKeyName: "topics_subject_id_fkey";
            columns: ["subject_id"];
            isOneToOne: false;
            referencedRelation: "subjects";
            referencedColumns: ["id"];
          },
        ];
      };
      user_roles: {
        Row: {
          id: string;
          role: Database["public"]["Enums"]["app_role"];
          user_id: string;
        };
        Insert: {
          id?: string;
          role?: Database["public"]["Enums"]["app_role"];
          user_id: string;
        };
        Update: {
          id?: string;
          role?: Database["public"]["Enums"]["app_role"];
          user_id?: string;
        };
        Relationships: [];
      };
    };
    Views: {
      [_ in never]: never;
    };
    Functions: {
      finalize_notebook_document: {
        Args: {
          p_notebook: string;
          p_path: string;
          p_name: string;
          p_size: number;
          p_mime: string;
          p_chunks: Json;
          p_error?: string | null;
        };
        Returns: Json;
      };
      evaluate_activity: {
        Args: { p_activity: string; p_answer: Json; p_learner: string };
        Returns: Json;
      };
      has_role: {
        Args: {
          _role: Database["public"]["Enums"]["app_role"];
          _user_id: string;
        };
        Returns: boolean;
      };
      release_order_stock: { Args: { p_order: string }; Returns: undefined };
      reserve_stock: { Args: { p_items: Json }; Returns: boolean };
      reserve_tutor_request: { Args: { p_user: string }; Returns: boolean };
    };
    Enums: {
      app_role: "admin" | "user";
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
};

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">;

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">];

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R;
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R;
      }
      ? R
      : never
    : never;

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I;
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I;
      }
      ? I
      : never
    : never;

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U;
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U;
      }
      ? U
      : never
    : never;

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    keyof DefaultSchema["Enums"] | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never;

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    keyof DefaultSchema["CompositeTypes"] | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never;

export const Constants = {
  public: {
    Enums: {
      app_role: ["admin", "user"],
    },
  },
} as const;
