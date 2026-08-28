window.WFGG_LASTWAR_COMPANION_AUTHORITATIVE_MAP={
  format:'WFGG_LASTWAR_COMPANION_AUTHORITATIVE_MAP_V1',
  source:{
    droneLevelTable:'lw_uav_level',
    dronePreviewTable:'lw_uav_level_preview',
    droneUpgradeTable:'lw_uav_upgrade',
    dominatorMainTable:'dominator_main',
    dominatorRankShowTable:'dominator_rank_show',
    basis:'decoded Lua 5.3 static table bytecode from installed Last War table container',
    networkUsed:false
  },
  drone:{
    uavId:1000,
    levelMilestones:[
      {minLevel:1,appearance:1201,icon:'FX_wurenji_pifu01'},
      {minLevel:50,appearance:1206,icon:'FX_wurenji_pifu02'},
      {minLevel:100,appearance:1211,icon:'FX_wurenji_pifu03'},
      {minLevel:150,appearance:1216,icon:'FX_wurenji_pifu04'},
      {minLevel:200,appearance:1221,icon:'FX_wurenji_pifu05'},
      {minLevel:250,appearance:1226,icon:'FX_wurenji_pifu06'}
    ],
    resolve(level){
      const n=Number(level)||0;
      const rows=this.levelMilestones.filter(x=>n>=x.minLevel);
      const base=rows.length?rows[rows.length-1]:this.levelMilestones[0];
      // Exact level 162 row in lw_uav_level: appearance 1217, skill 700105, skill level 7.
      return {...base,currentLevel:n,currentAppearance:n>=160&&n<170?1217:base.appearance};
    }
  },
  dominator:{
    familyId:1000000,
    familyName:'Gorilla',
    defaultAppearance:1000000,
    smallPicPath:'zxl_zhuzai_biandui',
    rankStages:[
      {minRank:0,starLevel:0,appearance:1000001,icon:'zxl_zhuzai_touxiang_00'},
      {minRank:10,starLevel:1,appearance:1000002,icon:'zxl_zhuzai_touxiang_01'},
      {minRank:20,starLevel:2,appearance:1000003,icon:'zxl_zhuzai_touxiang_02'},
      {minRank:30,starLevel:3,appearance:1000004,icon:'zxl_zhuzai_touxiang_03'},
      {minRank:40,starLevel:4,appearance:1000005,icon:'zxl_zhuzai_touxiang_04'},
      {minRank:50,starLevel:5,appearance:1000006,icon:'zxl_zhuzai_touxiang_05'},
      {minRank:60,starLevel:6,appearance:1000007,icon:'zxl_zhuzai_touxiang_06'}
    ],
    resolve(rank){
      const n=Number(rank)||0;
      const rows=this.rankStages.filter(x=>n>=x.minRank);
      return {...(rows.length?rows[rows.length-1]:this.rankStages[0]),currentRank:n};
    }
  }
};
