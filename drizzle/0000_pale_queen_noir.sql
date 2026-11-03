CREATE TABLE `agent_reservations` (
	`id` text PRIMARY KEY NOT NULL,
	`month` text NOT NULL,
	`day` text NOT NULL,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `agent_month_idx` ON `agent_reservations` (`month`);--> statement-breakpoint
CREATE INDEX `agent_day_idx` ON `agent_reservations` (`day`);