import {sqliteTable,text,integer,index} from 'drizzle-orm/sqlite-core';
export const agentReservations=sqliteTable('agent_reservations',{
  id:text('id').primaryKey(),month:text('month').notNull(),day:text('day').notNull(),createdAt:integer('created_at').notNull(),
},table=>[index('agent_month_idx').on(table.month),index('agent_day_idx').on(table.day)]);
