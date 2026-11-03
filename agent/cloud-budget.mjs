export const CLOUD_LIMITS=Object.freeze({monthlyRequests:100,dailyRequests:10,reservationUsd:0.02,monthlyReservationUsd:2});
export async function reserveCloudRequest(db,now=new Date()) {
  if(!db)throw new Error('Usage ledger is unavailable.');
  const month=now.toISOString().slice(0,7),day=now.toISOString().slice(0,10);
  const reserved=await db.prepare(`INSERT INTO agent_reservations(id,month,day,created_at)
    SELECT ?,?,?,? WHERE (SELECT COUNT(*) FROM agent_reservations WHERE month=?)<?
    AND (SELECT COUNT(*) FROM agent_reservations WHERE day=?)<? RETURNING id`)
    .bind(crypto.randomUUID(),month,day,now.getTime(),month,CLOUD_LIMITS.monthlyRequests,day,CLOUD_LIMITS.dailyRequests).first();
  if(!reserved)throw new Error('The analytics agent request allowance has been reached.');
  const counts=await db.prepare('SELECT (SELECT COUNT(*) FROM agent_reservations WHERE month=?) AS monthlyUsed,(SELECT COUNT(*) FROM agent_reservations WHERE day=?) AS dailyUsed').bind(month,day).first();
  return {...CLOUD_LIMITS,...counts};
}
